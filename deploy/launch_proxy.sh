#!/usr/bin/env bash
set -euo pipefail

: "${PD_PROXY_SCRIPT:?Set path to the proxy script from the vLLM Ascend revision in use}"
: "${PD_P_HOST:?Set the Prefill service address}"
: "${PD_D_HOST:?Set the Decode service address}"

p_hosts=() p_ports=() d_hosts=() d_ports=()
p_base_port=${PD_P_API_BASE_PORT:-7100}
d_base_port=${PD_D_API_BASE_PORT:-7100}
for ((rank=0; rank<4; rank++)); do
    p_hosts+=("$PD_P_HOST")
    p_ports+=("$((p_base_port + rank))")
done
for ((rank=0; rank<16; rank++)); do
    d_hosts+=("$PD_D_HOST")
    d_ports+=("$((d_base_port + rank))")
done

unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
exec python3 "$PD_PROXY_SCRIPT" \
    --host "${PD_PROXY_BIND_HOST:-$PD_P_HOST}" --port "${PD_PROXY_PORT:-8080}" \
    --prefiller-hosts "${p_hosts[@]}" --prefiller-ports "${p_ports[@]}" \
    --decoder-hosts "${d_hosts[@]}" --decoder-ports "${d_ports[@]}"
