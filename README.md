# BitTrickle: Peer‑to‑Peer File Sharing

A lightweight, **permissioned P2P file‑sharing app** in Python. A small central server provides **authentication & discovery** over UDP; peers **transfer files directly** over TCP. Built for clarity to showcase systems, networking, and concurrency skills—without unnecessary complexity.

---

## Overview
- **Client–server + peer‑to‑peer**: the server authenticates users and tracks which peer has which file; clients publish/search and fetch files directly from peers.
- **Protocols**: UDP for control (client⇄server), TCP for data (peer⇄peer).
- **Concurrency**: a multithreaded client keeps the shell responsive while sending heartbeats and serving incoming downloads.

---

## Code Layout & Dependencies
```
.
├── server.py   # central index/auth server (UDP)
└── client.py   # interactive client (UDP control, TCP data)
```
- **Language**: Python 3
- **Stdlib only**: `socket`, `threading`, `argparse`, `os`, `time`

---

## How It Works
**Server (single‑threaded UDP):**
- Authenticates users and maintains the network index.
- Responds to client operations (publish/unpublish/search/list/get).
- **Liveness policy**: instead of a dedicated heartbeat checker, the server validates a client’s **last heartbeat timestamp** right before handling each request and removes stale clients first.

**Client (multithreaded):**
- **Main (UDP_Client)**: logs in and handles the interactive commands.
- **Heartbeat thread**: sends a heartbeat to the server **every ~2s**.
- **TCP server thread**: listens for inbound file requests and uses a **fixed thread‑pool (5 workers)** to handle transfers concurrently.
- Includes a **graceful shutdown** helper so threads and sockets close cleanly.

**End‑to‑end flow example:**
1) A publishes `X.mp3`. 2) B searches and learns A has it. 3) B opens **TCP** to A and downloads it.

---

## Data Structures (Server)
- **Credentials**: `username → password`
- **Active clients**: `username → { udp_address, tcp_address, last_heartbeat }`
- **Published files**: `filename → { usernames… }`  (who currently publishes each file)

---

## Application Protocol (Control Plane over UDP)
**Core Commands (Client Shell)**
- `login <username> <password> <tcp_port>`
- `heartbeat <username>`
- `lap <username>` – list active peers
- `pub <username> <filename>` / `unp <username> <filename>`
- `lpf <username>` – list this peer’s published files
- `sch <username> <substring>` – substring search
- `get <username> <filename>` – ask where to fetch a file
- `xit` – graceful exit

**Server responses**
- `OK ...` or `Error ...` messages for all commands
- For `get`: `200 <peer_ip> <tcp_port>` so the client can open a TCP connection to the peer

---

## Quickstart
> Assumes Python 3.x and local demo on one machine (loopback).

1) **Prepare credentials** (server working dir)
```
server/
└── credentials.txt   # one "username password" per line
```
2) **Run server**
```bash
cd server
python3 ../server.py <server_port>
```
3) **Run client** (in a directory that contains files you want to share)
```bash
python3 client.py <server_port>
```
- Log in using an entry from `server/credentials.txt`.
- Start multiple clients in separate terminals to see peer‑to‑peer transfers.

---

## Known Limitations (and Possible Extensions)
- **Concurrency bound**: inbound transfers handled by a **5‑worker** pool.
- **File checks**: server trusts client publications; clients check local presence before publishing.
- **Resilience**: no TLS, no NAT traversal, no resume/retry on interrupted TCP transfers.
- **Error handling**: intentionally minimal for instructional clarity.

**Future work**: TLS, resumable/chunked downloads, richer search, rate limiting, persistent server state, tests & CI.

---

## What This Demonstrates
- Networking fundamentals (custom app protocol over UDP/TCP)
- Safe multithreading and coordination (heartbeat + thread‑pool)
- Clear separation of **auth/indexing** (server) vs **data transfer** (peers)
