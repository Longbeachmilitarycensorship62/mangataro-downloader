#!/usr/bin/env bash
# Generates the Xray server/client configs and the vless:// share URI.
#
# Transport choice is constrained by how Cloudflare carries the connection:
#
#   ws, httpupgrade  Both perform a 101 upgrade, which turns the connection into
#                    a raw bidirectional pipe the edge passes through untouched.
#                    These are the only transports a QUICK TUNNEL can carry.
#
#   xhttp            Stays pure HTTP. Works on a real zone, but a quick tunnel
#                    withholds a response body until 131072 bytes accumulate and
#                    never streams small writes, which deadlocks the downlink:
#                    the few KB of TLS handshake sit in the buffer, so traffic
#                    never reaches the threshold that would flush it. Named mode
#                    only, and packet-up only (stream-up/one need a streaming
#                    request body, which Cloudflare buffers).
#
#   Reality/Vision, raw TCP, mKCP, QUIC
#                    Impossible either way. Cloudflare terminates TLS at its own
#                    edge, so Reality's handshake never reaches the origin —
#                    measured: "remote error: tls: handshake failure", origin saw
#                    no connection at all.

# Cloudflare terminates TLS at the edge, so the inbound is plaintext on
# loopback. cloudflared is the only thing that ever connects to it.
#
# sockopt.trustedXForwardedFor takes HEADER NAMES, not IPs: Xray trusts the
# X-Forwarded-For value only when one of these headers is present. CF-Connecting-IP
# is always set by Cloudflare, so it works as the "this came via CF" marker and
# stops the per-connection "X-Forwarded-For ... is not configured" warning.

# Emits the streamSettings block for the chosen transport.
# $1 = "server" | "client", $2 = public hostname (client only)
qt_stream_settings() {
  local side="$1" host="${2:-}"
  case "${QT_TRANSPORT:-ws}" in
    httpupgrade)
      if [ "$side" = server ]; then
        printf '"network": "httpupgrade", "security": "none",\n      "httpupgradeSettings": { "path": "%s" }' "$QT_WSPATH"
      else
        printf '"network": "httpupgrade", "security": "tls",\n      "tlsSettings": { "serverName": "%s", "alpn": ["http/1.1"] },\n      "httpupgradeSettings": { "path": "%s", "host": "%s" }' "$host" "$QT_WSPATH" "$host"
      fi ;;
    xhttp)
      if [ "$side" = server ]; then
        printf '"network": "xhttp", "security": "none",\n      "xhttpSettings": { "path": "%s", "mode": "auto" }' "$QT_WSPATH"
      else
        printf '"network": "xhttp", "security": "tls",\n      "tlsSettings": { "serverName": "%s" },\n      "xhttpSettings": { "path": "%s", "host": "%s", "mode": "packet-up" }' "$host" "$QT_WSPATH" "$host"
      fi ;;
    *)
      if [ "$side" = server ]; then
        printf '"network": "ws", "security": "none",\n      "wsSettings": { "path": "%s", "heartbeatPeriod": %s }' "$QT_WSPATH" "$QT_HEARTBEAT"
      else
        printf '"network": "ws", "security": "tls",\n      "tlsSettings": { "serverName": "%s", "alpn": ["http/1.1"] },\n      "wsSettings": { "path": "%s", "host": "%s", "heartbeatPeriod": %s }' "$host" "$QT_WSPATH" "$host" "$QT_HEARTBEAT"
      fi ;;
  esac
}

qt_gen_server() {
  mkdir -p "$QT_ETC"
  cat > "$QT_ETC/server.json" <<JSON
{
  "log": { "loglevel": "warning", "access": "$QT_LOG/access.log", "error": "$QT_LOG/error.log" },
  "inbounds": [{
    "tag": "in-$QT_TRANSPORT",
    "listen": "127.0.0.1",
    "port": $QT_PORT,
    "protocol": "vless",
    "settings": { "clients": [{ "id": "$QT_UUID" }], "decryption": "none" },
    "streamSettings": {
      $(qt_stream_settings server),
      "sockopt": { "trustedXForwardedFor": ["CF-Connecting-IP"] }
    }
  }],
  "outbounds": [{ "protocol": "freedom", "tag": "direct" }]
}
JSON
  chmod 600 "$QT_ETC/server.json"
}

# $1 = public hostname
qt_gen_client() {
  local host="$1"
  mkdir -p "$QT_ETC"
  cat > "$QT_ETC/client.json" <<JSON
{
  "log": { "loglevel": "warning" },
  "inbounds": [{
    "tag": "socks-in",
    "listen": "127.0.0.1",
    "port": $QT_SOCKS_PORT,
    "protocol": "socks",
    "settings": { "udp": true, "auth": "noauth" }
  }],
  "outbounds": [{
    "tag": "proxy",
    "protocol": "vless",
    "settings": { "vnext": [{
      "address": "$host",
      "port": 443,
      "users": [{ "id": "$QT_UUID", "encryption": "none" }]
    }]},
    "streamSettings": {
      $(qt_stream_settings client "$host")
    }
  }]
}
JSON
  chmod 600 "$QT_ETC/client.json"
}

# Builds the share URI.
#
# sni= and host= are omitted: both equal the address, and Xray already falls
# back that way — wsSettings.Host -> tlsSettings.ServerName -> destination
# address (websocket/dialer.go), and an empty ServerName is set to the
# destination address (tls/config.go). Dropping them removes three copies of a
# ~40-char hostname, which is what keeps the QR small. Pass "full" to spell
# them out anyway.
#
# alpn is pinned to http/1.1 for the 101-upgrade transports: Xray otherwise
# offers h2, and a negotiated h2 breaks the HTTP/1.1 upgrade at the edge. XHTTP
# wants h2, so it is left off there.
qt_build_link() {
  local host="$1" form="${2:-short}" encpath remark extra='' params
  encpath="${QT_WSPATH//\//%2F}"
  remark="$(qt_urlencode "${QT_REMARK:-quicktunnel}")"
  case "${QT_TRANSPORT:-ws}" in
    httpupgrade) params="type=httpupgrade&alpn=http%2F1.1&fp=chrome&path=$encpath" ;;
    xhttp)       params="type=xhttp&mode=packet-up&fp=chrome&path=$encpath" ;;
    *)           params="type=ws&alpn=http%2F1.1&fp=chrome&path=$encpath" ;;
  esac
  if [ "$form" = full ]; then
    extra="&sni=$host&host=$host"
  fi
  printf 'vless://%s@%s:443?encryption=none&security=tls&%s%s#%s' \
    "$QT_UUID" "$host" "$params" "$extra" "$remark"
}

# Percent-encode anything outside the unreserved set, so a remark may contain
# spaces or non-ASCII without breaking the URI fragment.
#
# LC_ALL=C makes `?` match one BYTE rather than one character, so multi-byte
# UTF-8 is encoded per byte as RFC 3986 requires. Uses only POSIX parameter
# expansion — ${s:i:1} is bash-only and silently misbehaves under zsh.
qt_urlencode() {
  local LC_ALL=C s="$1" out='' c
  while [ -n "$s" ]; do
    c="${s%"${s#?}"}"
    s="${s#?}"
    case "$c" in
      [A-Za-z0-9.~_-]) out="$out$c" ;;
      # & 0xFF because bash treats a high byte as a signed char and would
      # otherwise emit a sign-extended %FFFFFFFFFFFFFFD9 instead of %D9.
      *) out="$out$(printf '%%%02X' "$(( $(printf '%d' "'$c") & 0xFF ))")" ;;
    esac
  done
  printf '%s' "$out"
}

qt_write_state() {
  local host="$1"
  mkdir -p "$QT_RUN"
  printf '%s\n' "$host" > "$QT_RUN/hostname"
  qt_build_link "$host" > "$QT_RUN/link.txt"
  printf '\n' >> "$QT_RUN/link.txt"
  chmod 600 "$QT_RUN/link.txt"
}
