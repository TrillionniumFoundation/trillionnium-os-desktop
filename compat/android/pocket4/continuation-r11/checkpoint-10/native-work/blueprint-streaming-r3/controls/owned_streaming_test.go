// Copyright 2026 The DroidLoom Authors.
// SPDX-License-Identifier: Apache-2.0

// This test is compiled inside the complete, copied, hash-inventoried Blueprint
// package. It uses the real parser, action generation, serializers and filesystem.
// No production function is replaced by a test implementation.
package blueprint

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"hash"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strconv"
	"strings"
	"syscall"
	"testing"
)

var ownedStreamingPackage = NewPackageContext("github.com/google/blueprint/ownedstreaming")

type ownedStreamingConfig struct{}

func (ownedStreamingConfig) IsActionSandboxedBuild() bool { return false }
func (ownedStreamingConfig) ActionSandboxMetrics() *SandboxMetrics { return nil }

type ownedStreamingModule struct {
	ModuleBase
	SimpleName
	Properties struct {
		Mode string
		Payload string
		Edges string
	}
}

func ownedStreamingFactory() (Module, []interface{}) {
	m := &ownedStreamingModule{}
	return m, []interface{}{&m.SimpleName.Properties, &m.Properties}
}

func (m *ownedStreamingModule) GenerateBuildActions(ctx ModuleContext) {
	if m.Properties.Mode == "empty" {
		return
	}
	ctx.Variable(ownedStreamingPackage, "owned_payload", "owned $$ literal with spaces")
	if m.Properties.Mode == "variable" {
		return
	}
	rule := ctx.Rule(ownedStreamingPackage, "owned_rule", RuleParams{
		Command: "echo $owned_payload $owned_arg $in > $out",
		Description: "owned stream $out",
		Comment: "owned fixture rule; serialization only, never executed",
		Restat: true,
	}, "owned_arg")
	if m.Properties.Mode == "rule" {
		return
	}
	edges, err := strconv.Atoi(m.Properties.Edges)
	if err != nil || edges < 1 || edges > 64 {
		panic("invalid fixed owned fixture edge count")
	}
	for i := 0; i < edges; i++ {
		name := fmt.Sprintf("%s-%03d", m.Name(), i)
		ctx.Build(ownedStreamingPackage, BuildParams{
			Rule: rule,
			Comment: "owned comment with unicode λ and newline\nsecond line " + name,
			Outputs: []string{"out/" + name + ":with space"},
			ImplicitOutputs: []string{"implicit/" + name},
			Inputs: []string{"in/" + name, "long/" + m.Properties.Payload},
			Implicits: []string{"implicit-input/" + name},
			OrderOnly: []string{"shared-order-a", "shared-order-b"},
			Validations: []string{"validation/" + name},
			Args: map[string]string{"owned_arg": "owned argument"},
			Default: i == 0,
		})
	}
}

type ownedStreamingSpec struct {
	name string
	modules int
	payloadBytes int
	edges int
	mixed bool
}

func ownedStreamingPrepare(t *testing.T, spec ownedStreamingSpec) (*Context, string, []*moduleInfo) {
	return ownedStreamingPrepareMode(t, spec, false)
}

func ownedStreamingPrepareMode(t *testing.T, spec ownedStreamingSpec, incremental bool) (*Context, string, []*moduleInfo) {
	t.Helper()
	ctx := NewContext()
	if ctx.GetIncrementalEnabled() {
		t.Fatal("incremental mode is not disabled by default")
	}
	actualFS := ctx.fs
	ctx.RegisterModuleType("owned_stream_module", ownedStreamingFactory)
	var bp strings.Builder
	for i := spec.modules - 1; i >= 0; i-- {
		mode := "build"
		if spec.mixed {
			mode = []string{"empty", "variable", "rule", "build", "build"}[i % 5]
		}
		fmt.Fprintf(&bp, "owned_stream_module { name: %q, mode: %q, payload: %q, edges: %q, }\n",
			fmt.Sprintf("module-%04d", i), mode, strings.Repeat("x", spec.payloadBytes), strconv.Itoa(spec.edges))
	}
	ctx.MockFileSystem(map[string][]byte{"Android.bp": []byte(bp.String())})
	config := ownedStreamingConfig{}
	if _, errs := ctx.ParseBlueprintsFiles("Android.bp", config); len(errs) != 0 {
		t.Fatalf("real parse failed: %v", errs)
	}
	if _, errs := ctx.ResolveDependencies(config); len(errs) != 0 {
		t.Fatalf("real dependency resolution failed: %v", errs)
	}
	directory := t.TempDir()
	ctx.SetFs(actualFS)
	ctx.SetSrcDir(directory)
	ctx.SetIncrementalDBDir("owned-cache")
	ctx.SetIncrementalEnabled(incremental)
	if _, errs := ctx.PrepareBuildActions(config); len(errs) != 0 {
		t.Fatalf("real action generation failed: %v", errs)
	}
	if ctx.keyValueStoreCache != nil {
		t.Cleanup(func() {
			if err := ctx.keyValueStoreCache.close(); err != nil {
				t.Errorf("owned incremental cache close failed: %v", err)
			}
		})
	}
	if ctx.GetIncrementalEnabled() != incremental || ctx.GetIncrementalAnalysis() || ctx.incrementalProviderTest {
		t.Fatal("fixture mode does not match the requested fresh-generation mode")
	}
	var modules []*moduleInfo
	for m := range ctx.iterateAllVariants() {
		if m.buildActionCacheKey != nil || m.incrementalRestored {
			t.Fatal("nonincremental fixture unexpectedly has a cache key or restored module")
		}
		modules = append(modules, m)
	}
	slices.SortFunc(modules, func(a, b *moduleInfo) int {
		return strings.Compare(a.cachedUniqueName, b.cachedUniqueName)
	})
	return ctx, directory, modules
}

func ownedStreamingArtifactRoot(t *testing.T) string {
	t.Helper()
	root := os.Getenv("POCKET4_WRITER_ARTIFACTS")
	if root == "" || !filepath.IsAbs(root) {
		t.Fatal("explicit absolute owned artifact root is required")
	}
	st, err := os.Lstat(root)
	if err != nil || !st.IsDir() || st.Mode() & os.ModeSymlink != 0 {
		t.Fatal("owned artifact root must already be a real directory")
	}
	return root
}

func ownedStreamingSave(t *testing.T, name string, data []byte) {
	t.Helper()
	path := filepath.Join(ownedStreamingArtifactRoot(t), name)
	f, err := os.OpenFile(path, os.O_WRONLY | os.O_CREATE | os.O_EXCL, 0600)
	if err != nil {
		t.Fatal(err)
	}
	_, writeErr := f.Write(data)
	closeErr := f.Close()
	if writeErr != nil || closeErr != nil {
		t.Fatalf("artifact write/close: %v / %v", writeErr, closeErr)
	}
}

func TestPocket4StreamingWholeShardOutput(t *testing.T) {
	specs := []ownedStreamingSpec{
		{"zero", 0, 1, 1, false},
		{"one", 1, 31, 1, false},
		{"nine", 9, 257, 2, true},
		{"ten", 10, 257, 2, true},
		{"eleven", 11, 257, 2, true},
		{"mixed37", 37, 257, 3, true},
		{"large", 13, 65536, 3, false},
		{"enabled13", 13, 257, 3, false},
	}
	for _, spec := range specs {
		t.Run(spec.name, func(t *testing.T) {
			ctx, directory, _ := ownedStreamingPrepareMode(t, spec, spec.name == "enabled13")
			var main bytes.Buffer
			if err := ctx.WriteBuildFile(&main, true, "build.ninja"); err != nil {
				t.Fatalf("actual sharded WriteBuildFile failed: %v", err)
			}
			ownedStreamingSave(t, spec.name + ".main.ninja", main.Bytes())
			var present []string
			for _, file := range GetNinjaShardFiles("build.ninja") {
				data, err := os.ReadFile(filepath.Join(directory, file))
				if errors.Is(err, os.ErrNotExist) {
					continue
				}
				if err != nil {
					t.Fatal(err)
				}
				present = append(present, file)
				ownedStreamingSave(t, spec.name + "." + file, data)
			}
			if spec.modules > 0 && len(present) == 0 {
				t.Fatal("no actual shard produced for nonempty input")
			}
			list, err := json.Marshal(present)
			if err != nil {
				t.Fatal(err)
			}
			ownedStreamingSave(t, spec.name + ".shards.json", append(list, '\n'))
		})
	}
}

func TestPocket4StreamingRealSerializerEquivalence(t *testing.T) {
	for _, spec := range []ownedStreamingSpec{
		{"empty", 0, 1, 1, false},
		{"mixed", 37, 257, 3, true},
		{"large", 7, 131072, 3, false},
	} {
		t.Run(spec.name, func(t *testing.T) {
			ctx, _, modules := ownedStreamingPrepare(t, spec)
			var oldOutput, streamingOutput bytes.Buffer
			if err := ctx.writeIncrementalModules(modules, newNinjaWriter(&oldOutput)); err != nil {
				t.Fatal(err)
			}
			if err := ctx.writeModuleAction(modules, newNinjaWriter(&streamingOutput)); err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(oldOutput.Bytes(), streamingOutput.Bytes()) {
				t.Fatalf("actual serializers differ: buffered=%d, streaming=%d", oldOutput.Len(), streamingOutput.Len())
			}
			if len(modules) > 0 && oldOutput.Len() == 0 {
				t.Fatal("nonempty serializer comparison was vacuous")
			}
			t.Logf("same_bytes=%d sha256=%x", oldOutput.Len(), sha256.Sum256(oldOutput.Bytes()))
		})
	}
}

type ownedFailWriter struct {
	remaining int
	written int
}

func (w *ownedFailWriter) Write(data []byte) (int, error) {
	n := len(data)
	if n > w.remaining {
		n = w.remaining
		w.remaining = 0
		w.written += n
		return n, syscall.ENOSPC
	}
	w.remaining -= n
	w.written += n
	return n, nil
}

func (w *ownedFailWriter) WriteString(text string) (int, error) { return w.Write([]byte(text)) }

func TestPocket4StreamingWriterErrors(t *testing.T) {
	ctx, _, modules := ownedStreamingPrepare(t, ownedStreamingSpec{"errors", 5, 8192, 3, false})
	var complete bytes.Buffer
	if err := ctx.writeModuleAction(modules, newNinjaWriter(&complete)); err != nil {
		t.Fatal(err)
	}
	for _, limit := range []int{0, 11, complete.Len()/2, complete.Len()-1} {
		t.Run(strconv.Itoa(limit), func(t *testing.T) {
			streaming := &ownedFailWriter{remaining: limit}
			err := ctx.writeModuleAction(modules, newNinjaWriter(streaming))
			if !errors.Is(err, syscall.ENOSPC) || streaming.written != limit {
				t.Fatalf("actual streaming error not propagated: err=%v bytes=%d want=%d", err, streaming.written, limit)
			}
			buffered := &ownedFailWriter{remaining: limit}
			oldErr := ctx.writeIncrementalModules(modules, newNinjaWriter(buffered))
			if oldErr != nil || buffered.written != limit {
				t.Fatalf("pre-existing buffered write-error observation changed: err=%v bytes=%d", oldErr, buffered.written)
			}
			t.Logf("actual stream returns ENOSPC; existing buffered method discards it; accepted_bytes=%d", limit)
		})
	}
}

func TestPocket4StreamingShardOpenError(t *testing.T) {
	ctx, directory, _ := ownedStreamingPrepare(t, ownedStreamingSpec{"shard-errors", 20, 257, 2, false})
	for _, file := range GetNinjaShardFiles("build.ninja") {
		if err := os.Mkdir(filepath.Join(directory, file), 0700); err != nil {
			t.Fatal(err)
		}
	}
	var main bytes.Buffer
	if err := ctx.WriteBuildFile(&main, true, "build.ninja"); err == nil {
		t.Fatal("actual sharded writer accepted directories as writable shard files")
	} else {
		t.Logf("actual filesystem rejection joined and returned: %v", err)
	}
}

type ownedDigestWriter struct {
	h hash.Hash
	bytes uint64
	storage [4096]byte
}

func (w *ownedDigestWriter) Write(data []byte) (int, error) {
	n, err := w.h.Write(data)
	w.bytes += uint64(n)
	return n, err
}

func (w *ownedDigestWriter) WriteString(text string) (int, error) {
	// Avoid manufacturing a full output copy in the measurement sink.
	written := 0
	for len(text) > 0 {
		n := copy(w.storage[:], text)
		if _, err := w.h.Write(w.storage[:n]); err != nil {
			return written, err
		}
		text = text[n:]
		written += n
		w.bytes += uint64(n)
	}
	return written, nil
}

type ownedAllocationResult struct {
	Bytes uint64 `json:"output_bytes"`
	SHA256 string `json:"sha256"`
	Allocated uint64 `json:"total_alloc_delta"`
}

func ownedMeasure(t *testing.T, operation func(*ninjaWriter) error) ownedAllocationResult {
	t.Helper()
	runtime.GC()
	w := &ownedDigestWriter{h: sha256.New()}
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	if err := operation(newNinjaWriter(w)); err != nil {
		t.Fatal(err)
	}
	runtime.ReadMemStats(&after)
	return ownedAllocationResult{w.bytes, hex.EncodeToString(w.h.Sum(nil)), after.TotalAlloc - before.TotalAlloc}
}

func TestPocket4StreamingAllocationControl(t *testing.T) {
	ctx, _, modules := ownedStreamingPrepare(t, ownedStreamingSpec{"allocation", 32, 262144, 1, false})
	buffered := ownedMeasure(t, func(w *ninjaWriter) error { return ctx.writeIncrementalModules(modules, w) })
	streamed := ownedMeasure(t, func(w *ninjaWriter) error { return ctx.writeModuleAction(modules, w) })
	if buffered.Bytes < 8*1024*1024 || buffered.Bytes != streamed.Bytes || buffered.SHA256 != streamed.SHA256 {
		t.Fatalf("allocation comparison has unequal or vacuous output: buffered=%+v streamed=%+v", buffered, streamed)
	}
	if buffered.Allocated <= streamed.Allocated || buffered.Allocated-streamed.Allocated < buffered.Bytes {
		t.Fatalf("did not observe removal of at least one full output allocation: buffered=%+v streamed=%+v", buffered, streamed)
	}
	report := map[string]interface{}{
		"scope": "actual serializer TotalAlloc comparison; not full-build peak or OOM-victim proof",
		"go_version": runtime.Version(),
		"runtime_NumCPU": runtime.NumCPU(),
		"parallelVisitLimit": parallelVisitLimit,
		"buffered": buffered,
		"streamed": streamed,
	}
	data, err := json.Marshal(report)
	if err != nil {
		t.Fatal(err)
	}
	t.Log(string(data))
}

func TestPocket4StreamingWholePathAllocation(t *testing.T) {
	ctx, directory, _ := ownedStreamingPrepare(t, ownedStreamingSpec{"full-allocation", 20, 262144, 1, false})
	var main bytes.Buffer
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	err := ctx.WriteBuildFile(&main, true, "build.ninja")
	runtime.ReadMemStats(&after)
	if err != nil {
		t.Fatal(err)
	}
	outputBytes := uint64(main.Len())
	ownedStreamingSave(t, "memoryfull.main.ninja", main.Bytes())
	for _, file := range GetNinjaShardFiles("build.ninja") {
		data, err := os.ReadFile(filepath.Join(directory, file))
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			t.Fatal(err)
		}
		outputBytes += uint64(len(data))
		ownedStreamingSave(t, "memoryfull." + file, data)
	}
	if outputBytes < 5*1024*1024 {
		t.Fatal("whole-path allocation comparison produced insufficient output")
	}
	report := map[string]interface{}{
		"scope": "actual WriteBuildFile TotalAlloc; compare separate matched baseline/candidate executions",
		"output_bytes": outputBytes,
		"total_alloc_delta": after.TotalAlloc - before.TotalAlloc,
		"go_version": runtime.Version(),
		"runtime_NumCPU": runtime.NumCPU(),
		"parallelVisitLimit": parallelVisitLimit,
		"incremental_enabled": ctx.GetIncrementalEnabled(),
	}
	data, err := json.Marshal(report)
	if err != nil {
		t.Fatal(err)
	}
	ownedStreamingSave(t, "metrics-full.json", append(data, '\n'))
	t.Log(string(data))
}
