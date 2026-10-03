# Run llama-server

> How-to guide. Validated command line, from live validation on 2026-10-02.

```bash
llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk q8_0 -ctv q4_0 -t 4
```

- Endpoint: `http://127.0.0.1:8080`
- Model: `unsloth/gpt-oss-20b-GGUF` (GPT-OSS 20B)
- `-t 4`: four threads (CPU-only host; adjust to your machine)
- `-ctk q8_0 -ctv q4_0`: KV cache quantization

Health check:

```bash
curl -s localhost:8080/health
# loading: {"error":{"message":"Loading model"...}}  (HTTP 503)
# loaded:  {"status":"ok"}                            (HTTP 200)
```

## Run as a systemd service

For a persistent install, wrap the command in a systemd user unit.
Example `~/.config/systemd/user/llama-server.service`:

```ini
[Unit]
Description=llama-server (GPT-OSS 20B)
After=network-online.target

[Service]
ExecStart=/path/to/llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk q8_0 -ctv q4_0 -t 4
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

Enable and start it, then check health:

```bash
systemctl --user daemon-reload
systemctl --user enable --now llama-server
systemctl --user status llama-server
curl -s localhost:8080/health
```

Note: systemd restart/recovery has not been covered by the live test suite.
