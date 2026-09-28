#!/bin/sh
# Put a mix under a video, loudness-mastered with a single linear gain change (master.sh does that part).
#   sh mux.sh video.mp4 mix.wav out.mp4 [target_LUFS=-14] [true_peak_dBTP=-1]
# -14 LUFS suits YouTube/Spotify/social; -16 podcasts/Apple; -23 (EBU R128) or -24 (ATSC, with -2 dBTP) broadcast.
# master.sh measures, refuses a target that would need more gain than the true-peak limit allows (and names the
# loudest reachable one), and writes the gained wav; this script copies the video stream and encodes that audio to
# AAC 256k. AAC can add small overs (a few tenths of a dB), which the -1 dBTP default leaves room for; the result
# is re-measured and printed.
# The output is never one of the inputs (symlinks and hard links included) and appears only once complete.
# Exit status: 0 = written and measured; 1 = input problem or unreachable target, explained as "error: ... / fix: ...".
V="$1"; A="$2"; O="$3"; I="${4:--14}"; TP="${5:--1}"
err() { printf 'error: %s\n' "$1" >&2; [ -n "$2" ] && printf '  fix: %s\n' "$2" >&2; exit 1; }

[ -n "$O" ] || err "usage: sh mux.sh video.mp4 mix.wav out.mp4 [LUFS] [dBTP]"
command -v ffmpeg >/dev/null 2>&1 || err "ffmpeg is not on PATH" "install it (macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)"
[ -f "$V" ] || err "video not found: $V" "check the path"
[ -d "$(dirname "$O")" ] || err "output folder does not exist: $(dirname "$O")" "create it first"
{ [ "$V" -ef "$O" ] || [ "$A" -ef "$O" ]; } && err "output is one of the inputs (same file, maybe via a symlink or hard link): $O" \
  "write to a new file, e.g. final.mp4"

# the mp4 is written next to its destination under a temp name (same extension, so ffmpeg picks the container) and
# moved into place only when complete: a failed or interrupted run leaves no partial file
TMP=$(mktemp -d); PART="$(dirname "$O")/.mux.$$.$(basename "$O")"
trap 'rm -rf "$TMP"; rm -f "$PART"' EXIT; trap 'exit 1' INT TERM HUP
sh "$(dirname "$0")/master.sh" "$A" "$TMP/master.wav" "$I" "$TP" >"$TMP/master.log" || exit 1
ffmpeg -y -loglevel error -i "$V" -i "$TMP/master.wav" \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 256k -movflags +faststart -shortest "$PART" >"$TMP/log" 2>&1 \
  || err "ffmpeg failed while writing $O: $(head -3 "$TMP/log" | tr '\n' ' ')" "check that $V has a video stream and that the folder for $O is writable"
# verify the finished mp4 (it decodes and its loudness can be measured) BEFORE it replaces anything at $O
ffmpeg -hide_banner -nostats -i "$PART" -af ebur128=peak=true:framelog=verbose -f null - >"$TMP/meter" 2>&1 \
  || err "the encoded file does not decode: $(grep -m1 -iE 'error|invalid' "$TMP/meter")" "rerun; if it persists, check disk space and the ffmpeg install"
M=$(awk '/Summary:/ { s = 1 } s && $1 == "I:" { i = $2 } s && $1 == "Peak:" { p = $2 } END { if (i != "" && p != "") print i, p }' "$TMP/meter")
[ -n "$M" ] || err "could not measure the encoded file's loudness" "rerun; if it persists, check the ffmpeg install"
mv -f "$PART" "$O" || err "could not move the result into place: $O" "check permissions on $O"
echo "$O"
sed 1d "$TMP/master.log"                                   # master.sh's gain and loudness line (its temp path dropped)
set -- $M; printf '  after AAC: %s LUFS, true peak %s dBTP\n' "$1" "$2"
