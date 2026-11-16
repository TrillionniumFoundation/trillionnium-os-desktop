// Copyright 2020 Google Inc. All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"os"
	"path"
	"time"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
)

var (
	target    = flag.String("target", "", "the target to fetch from")
	buildID   = flag.String("build_id", "", "the build id to fetch from, can use '-branch' to get the latest passed build ID")
	branch    = flag.String("branch", "", "the branch to fetch from, used when '-build_id' is not provided,\nit would fetch the latest successful build")
	artifact  = flag.String("artifact", "", "the artifact to download")
	output    = flag.String("output", "", "the file name to save as")
	clientID  = flag.String("client_id", "", "[Optional] OAuth 2.0 Client ID. Must be used with '-secret'")
	secret    = flag.String("secret", "", "[Optional] OAuth 2.0 Client Secret. Must be used with '-client_id'")
	port      = flag.Int("port", 10502, "[Optional] the port number where the oauth callback server would listen on")
	projectID = flag.String("project_id", "", "[Optional] the project id being used to access the fetch APIs.")
)

var writeToStdout = false

type BuildResponse struct {
	Builds []Build `json:"builds"`
}

type Build struct {
	BuildId string `json:"buildId"`
}

type Auth struct {
	clientID string
	secret   string
}

func newAuth(clientID, secret string) *Auth {
	return &Auth{clientID: clientID, secret: secret}
}

func newClient(ctx context.Context, auth *Auth) *http.Client {
	if auth == nil {
		return &http.Client{}
	}

	config := &oauth2.Config{
		ClientID:     auth.clientID,
		ClientSecret: auth.secret,
		Endpoint:     google.Endpoint,
		Scopes:       []string{"https://www.googleapis.com/auth/androidbuild.internal"},
	}
	return newOAuthClient(ctx, config)
}

type FetchConfig struct {
	client    *http.Client
	target    string
	buildID   string
	branch    string
	output    string
	artifact  string
	projectID string
	args      []string
}

func newFetchConfig(client *http.Client, target string, buildID string, branch string, output string, artifact string, projectID string, args []string) (*FetchConfig, error) {
	config := &FetchConfig{
		client:    client,
		target:    target,
		buildID:   buildID,
		branch:    branch,
		output:    output,
		artifact:  artifact,
		projectID: projectID,
		args:      args,
	}
	err := config.validate()
	if err != nil {
		return nil, err
	}
	return config, nil
}

func (c *FetchConfig) validate() error {
	// We only support passing 1 argument `-` so if we have more than
	// one argument this is an error state,
	if len(c.args) > 1 {
		return errors.New("too many arguments passed to fetch_artifact")
	}

	if len(c.args) > 0 {
		writeToStdout = c.args[len(c.args)-1] == "-"
		if !writeToStdout {
			return fmt.Errorf(
				"only supported final argument to fetch_artifact is `-` but got `%s`", c.args[len(c.args)-1])
		}

		if len(c.output) > 0 && writeToStdout {
			return errors.New("both '-output' and '-' flags can not be used together")
		}
	}

	// check user provided flags
	if len(c.target) == 0 {
		return errors.New("missing target")
	}
	if len(c.artifact) == 0 {
		return errors.New("missing artifact")
	}
	if len(c.buildID) == 0 && len(c.branch) == 0 {
		return errors.New("missing build_id or branch")
	}
	if len(c.buildID) != 0 && len(c.branch) != 0 {
		return errors.New("too many arguments, you should only give build_id or branch")
	}
	if len(c.buildID) == 0 {
		bid, err := getLatestGoodBuild(c)
		if err != nil {
			return err
		}
		c.buildID = bid
	}
	return nil
}

func errPrint(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	os.Exit(1)
}

func main() {
	flag.Parse()
	args := flag.Args()

	var auth *Auth
	if len(*clientID) != 0 && len(*secret) != 0 {
		auth = newAuth(*clientID, *secret)
	} else if len(*clientID) != 0 || len(*secret) != 0 {
		errPrint(fmt.Sprintf("missing client_id or client_secret."))
	}

	ctx := context.Background()
	client := newClient(ctx, auth)

	config, err := newFetchConfig(client, *target, *buildID, *branch, *output, *artifact, *projectID, args)
	if err != nil {
		errPrint(fmt.Sprintf("Config validation error: %s", err))
	}

	fetchArtifact(config)
}

func newOAuthClient(ctx context.Context, config *oauth2.Config) *http.Client {
	token := tokenFromWeb(ctx, config)
	return config.Client(ctx, token)
}

func tokenFromWeb(ctx context.Context, config *oauth2.Config) *oauth2.Token {
	ch := make(chan string)
	randState := fmt.Sprintf("st%d", time.Now().UnixNano())
	ts := createServer(ch, randState)
	go func() {
		err := ts.ListenAndServe()
		if err != http.ErrServerClosed {
			errPrint(fmt.Sprintf("Listen and serve error: %v", err))
		}
	}()

	defer ts.Close()
	config.RedirectURL = "http://localhost" + ts.Addr
	authURL := config.AuthCodeURL(randState)
	log.Printf("Authorize this app at: %s", authURL)
	code := <-ch

	token, err := config.Exchange(ctx, code)
	if err != nil {
		errPrint(fmt.Sprintf("Token exchange error: %v", err))

	}
	return token
}

func createServer(ch chan string, state string) *http.Server {
	return &http.Server{
		Addr:    fmt.Sprintf(":%d", *port),
		Handler: http.HandlerFunc(handler(ch, state)),
	}
}

func handler(ch chan string, randState string) func(http.ResponseWriter, *http.Request) {
	return func(rw http.ResponseWriter, req *http.Request) {
		if req.URL.Path == "/favicon.ico" {
			http.Error(rw, "error: visiting /favicon.ico", 404)
			return
		}
		if req.FormValue("state") != randState {
			log.Printf("state: %s doesn't match. (expected: %s)", req.FormValue("state"), randState)
			http.Error(rw, "invalid state", 500)
			return
		}
		if code := req.FormValue("code"); code != "" {
			fmt.Fprintf(rw, "<h1>Success</h1>Authorized.")
			rw.(http.Flusher).Flush()
			ch <- code
			return
		}
		ch <- ""
		http.Error(rw, "invalid code", 500)
	}
}

func sendRequest(client *http.Client, url string, projectID string) (*http.Response, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if len(projectID) != 0 {
		req.Header.Set("X-Goog-User-Project", projectID)
	}

	res, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	return res, nil
}

func fetchArtifact(c *FetchConfig) error {
	apiURL := fmt.Sprintf("https://androidbuild-pa.googleapis.com/v4/builds/%s/%s/attempts/latest/artifacts/%s/url", url.QueryEscape(c.buildID), url.QueryEscape(c.target), url.QueryEscape(c.artifact))
	res, err := sendRequest(c.client, apiURL, c.projectID)
	if err != nil {
		return fmt.Errorf("error fetching artifact %w", err)
	}
	defer res.Body.Close()

	if res.Status != "200 OK" {
		body, _ := ioutil.ReadAll(res.Body)
		errPrint(fmt.Sprintf("Unable to download artifact: %s\n %s.", res.Status, body))
	}

	if writeToStdout {
		io.Copy(os.Stdout, res.Body)
		return nil
	}

	fileName := c.artifact
	if len(c.output) > 0 {
		fileName = c.output
	}

	f, err := os.Create(path.Base(fileName))
	if err != nil {
		return fmt.Errorf("unable to create file %w", err)
	}
	defer f.Close()
	io.Copy(f, res.Body)
	fmt.Printf("File %s created.\n", f.Name())
	return nil
}

func getLatestGoodBuild(c *FetchConfig) (string, error) {
	apiURL := fmt.Sprintf("https://androidbuild-pa.googleapis.com/v4/builds?branches=%s&buildAttemptStatus=COMPLETE&buildType=SUBMITTED&pageSize=1&successful=true&targets=%s", url.QueryEscape(c.branch), url.QueryEscape(c.target))
	res, err := sendRequest(c.client, apiURL, c.projectID)
	if err != nil {
		return "", fmt.Errorf("send request error: %w", err)
	}
	defer res.Body.Close()

	if res.Status != "200 OK" {
		body, _ := ioutil.ReadAll(res.Body)
		return "", fmt.Errorf("unable to get Build ID: %s\n %s", res.Status, body)
	}

	body, _ := io.ReadAll(res.Body)
	var buildData BuildResponse
	err = json.Unmarshal(body, &buildData)

	if err != nil {
		return "", fmt.Errorf("error parsing JSON: %w", err)
	}
	if len(buildData.Builds) == 0 {
		return "", errors.New("error no build ID is found")
	}

	return buildData.Builds[0].BuildId, nil
}
