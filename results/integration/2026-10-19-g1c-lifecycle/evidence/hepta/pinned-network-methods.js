class PinnedNetwork {
    network_http_dispatch(entry) {
        if (this.webgl_context_lost || entry.state === "terminal") {
            return;
        }
        entry.state = "active";
        entry.controller = new AbortController();
        entry.started_at = performance.now();
        if (entry.is_archive_range) {
            let host = this.network_http_hosts.get(entry.host_key);
            if (!host.round) {
                host.round = {
                    started_at: entry.started_at,
                    ranges: 0,
                    bytes: 0,
                    tiles: new Set(),
                };
            }
            host.round.ranges += 1;
            for (const key of entry.tile_keys.split(",")) {
                if (key && key !== "-") {
                    host.round.tiles.add(key);
                }
            }
        }
        const arm_stall_timer = () => {
            if (this.webgl_context_lost || entry.state === "terminal") {
                return;
            }
            if (entry.stall_timer !== null) {
                window.clearTimeout(entry.stall_timer);
            }
            entry.stall_timer = window.setTimeout(() => {
                entry.controller.abort("HTTP request stalled for 20 seconds after dispatch");
            }, 20000);
        };
        arm_stall_timer();
        this.exports.wasm_network_http_progress(
            entry.request_id_lo,
            entry.request_id_hi,
            0,
            0
        );
        fetch(entry.fetch_url, {
            method: entry.method,
            headers: entry.headers,
            body: entry.body,
            signal: entry.controller.signal,
            redirect: "manual",
        }).then(async response => {
            if (this.webgl_context_lost || entry.state === "terminal") {
                return;
            }
            arm_stall_timer();
            let response_headers = "";
            response.headers.forEach((value, key) => {
                response_headers += `${key}: ${value}\r\n`;
            });
            const declared = response.headers.get("content-length");
            if (entry.method !== "HEAD" && declared !== null && Number(declared) > entry.max_body) {
                entry.controller.abort();
                throw "response body exceeds configured limit";
            }
            let chunks = [];
            let response_body_len = 0;
            if (response.body !== null) {
                const reader = response.body.getReader();
                for (;;) {
                    const item = await reader.read();
                    if (this.webgl_context_lost || entry.state === "terminal") {
                        return;
                    }
                    if (item.done) {
                        break;
                    }
                    arm_stall_timer();
                    response_body_len += item.value.byteLength;
                    if (response_body_len > entry.max_body) {
                        entry.controller.abort();
                        throw "response body exceeds configured limit";
                    }
                    chunks.push(item.value);
                }
            }
            let response_body = new Uint8Array(response_body_len);
            let body_at = 0;
            for (const chunk of chunks) {
                response_body.set(chunk, body_at);
                body_at += chunk.byteLength;
            }
            if (this.webgl_context_lost || entry.state === "terminal") {
                return;
            }
            let headers_u8 = this.string_to_u8(response_headers);
            let body_u8 = this.array_to_u8(response_body);
            entry.response_bytes = response_body.length;
            if (response.status >= 400) {
                console.error("[makepad][http][fail]", response.status, entry.fetch_url);
            }
            this.exports.wasm_network_http_response(
                entry.request_id_lo,
                entry.request_id_hi,
                entry.metadata_id_lo,
                entry.metadata_id_hi,
                response.status,
                headers_u8.ptr,
                headers_u8.len,
                body_u8.ptr,
                body_u8.len
            );
        }).catch(error => {
            if (this.webgl_context_lost || entry.state === "terminal") {
                return;
            }
            console.error(
                "[makepad][http][err]",
                entry.method,
                entry.fetch_url,
                "" + error,
                `tiles=${entry.tile_keys}`
            );
            let message_u8 = this.string_to_u8("" + error);
            this.exports.wasm_network_http_error(
                entry.request_id_lo,
                entry.request_id_hi,
                entry.metadata_id_lo,
                entry.metadata_id_hi,
                message_u8.ptr,
                message_u8.len
            );
        }).finally(() => {
            this.network_http_finish(entry);
        });
    }

    network_http_finish(entry) {
        if (entry.stall_timer !== null) {
            window.clearTimeout(entry.stall_timer);
            entry.stall_timer = null;
        }
        if (this.network_http_requests.get(entry.request_key) === entry) {
            this.network_http_requests.delete(entry.request_key);
        }
        entry.state = "done";
        if (this.webgl_context_lost) {
            return;
        }
        if (!entry.is_archive) {
            return;
        }
        const host = this.network_http_hosts.get(entry.host_key);
        if (!host) {
            return;
        }
        host.active = Math.max(0, host.active - 1);
        host.pending = Math.max(0, host.pending - 1);
        if (host.round && entry.is_archive_range) {
            host.round.bytes += entry.response_bytes;
        }
        this.network_http_pump(entry.host_key);
        if (host.pending === 0) {
            if (host.round) {
                host.round = null;
            }
            if (host.active === 0 && host.queue.length === 0) {
                this.network_http_hosts.delete(entry.host_key);
            }
        }
    }

    js_network_http_cancel(request_id_lo, request_id_hi) {
        let request_key = this.id_to_key(request_id_lo, request_id_hi);
        let entry = this.network_http_requests.get(request_key);
        if (!entry) {
            return;
        }
        if (entry.is_archive && entry.state === "queued") {
            const host = this.network_http_hosts.get(entry.host_key);
            if (host) {
                host.queue = host.queue.filter(item => item !== entry);
                host.pending = Math.max(0, host.pending - 1);
                if (host.pending === 0 && host.round) {
                    host.round = null;
                }
            }
            this.network_http_requests.delete(request_key);
            entry.state = "cancelled";
            const message_u8 = this.string_to_u8("HTTP request cancelled before dispatch");
            this.exports.wasm_network_http_error(
                entry.request_id_lo,
                entry.request_id_hi,
                entry.metadata_id_lo,
                entry.metadata_id_hi,
                message_u8.ptr,
                message_u8.len
            );
            if (host && host.pending === 0 && host.active === 0) {
                this.network_http_hosts.delete(entry.host_key);
            }
            return;
        }
        if (entry.is_archive && entry.state === "active") {
            return;
        }
        entry.controller.abort();
        this.network_http_requests.delete(request_key);
    }

}
window.PinnedNetwork = PinnedNetwork;

