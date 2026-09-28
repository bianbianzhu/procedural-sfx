#!/bin/sh
# Put a mix under a video with two-pass loudness normalisation.
#   sh mux.sh video.mp4 mix.wav out.mp4 [target_LUFS=-14] [true_peak_dBTP=-1]
# -14 LUFS suits YouTube/Spotify/social; -16 podcasts/Apple; -23 (EBU R128) or -24 (ATSC, with -2 dBTP) broadcast.
# Pass 1 measures, pass 2 corrects (lands within about +-0.5 LU; a single pass drifts further).
# Exit status: 0 = written and measured; 1 = input problem, explained as "error: ... / fix: ...".
V="$1"; A="$2"; O="$3"; I="${4:--14}"; TP="${5:--1}"
err() { printf 'error: %s\n' "$1" >&2; [ -n "$2" ] && printf '  fix: %s\n' "$2" >&2; exit 1; }

[ -n "$O" ] || err "usage: sh mux.sh video.mp4 mix.wav out.mp4 [LUFS] [dBTP]"
command -v ffmpeg >/dev/null 2>&1 || err "ffmpeg is not on PATH" "install it (macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)"
[ -f "$V" ] || err "video not found: $V" "check the path"
[ -f "$A" ] || err "audio not found: $A" "check the path; mix.py writes to its -o path"

LOG=$(mktemp); trap 'rm -f "$LOG"' EXIT
ffmpeg -hide_banner -nostats -i "$A" -af "loudnorm=I=$I:TP=$TP:LRA=11:print_format=json" -f null - >"$LOG" 2>&1 \
  || err "ffmpeg could not read $A: $(grep -m1 -iE 'error|invalid' "$LOG")" "check that it is a valid audio file"
g() { sed -n '/{/,/}/p' "$LOG" | grep "\"$1\"" | sed 's/.*: "\(.*\)".*/\1/'; }
MI=$(g input_i)
case "$MI" in
  ''|-inf|inf|nan) err "loudness of $A could not be measured (got '$MI')" \
                       "the mix is silent or shorter than ~0.4 s; check events and gains, or skip normalisation for a clip this short" ;;
esac
LN="loudnorm=I=$I:TP=$TP:LRA=11:measured_I=$MI:measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true"
ffmpeg -y -loglevel error -i "$V" -i "$A" \
  -filter_complex "[1:a]$LN,aresample=48000[a]" \
  -map 0:v:0 -map "[a]" -c:v copy -c:a aac -b:a 256k -movflags +faststart -shortest "$O" >"$LOG" 2>&1 \
  || err "ffmpeg failed while writing $O: $(head -3 "$LOG" | tr '\n' ' ')" "check that $V has a video stream and that the folder for $O exists"
echo "$O"
ffmpeg -hide_banner -nostats -i "$O" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I|LRA|Peak):" | head -3
