#!/bin/sh
# Put a mix under a video, loudness-mastered with a single linear gain change (master.sh does that part).
#   sh mux.sh video.mp4 mix.wav out.mp4 [target_LUFS=-14] [true_peak_dBTP=-1]
# -14 LUFS suits YouTube/Spotify/social; -16 podcasts/Apple; -23 (EBU R128) or -24 (ATSC, with -2 dBTP) broadcast.
# master.sh measures, refuses a target that would need more gain than the true-peak limit allows (and names the
# loudest reachable one), and writes the gained wav; this script copies the video stream and encodes that audio to
# AAC 256k.
# The video is the timeline: every video packet is copied (no -shortest, which drops the last frames of a copied
# B-frame stream when the audio ends at the same instant), and the audio is padded with silence or trimmed to the
# video's duration, with a warning when the mix length differs. The mix REPLACES any audio the video already has;
# a warning says so (to keep it, extract it and pass it to mix.py --music).
# Before the result replaces anything at the output path it is verified: same video packet count and duration as
# the source, audio as long as the video, loudness within 0.5 LU of the target and true peak at or under the limit
# after AAC (AAC can add a few tenths of a dB of overs; if it crosses the limit, nothing is written and the error
# names the quieter target that fits). Everything is built in a private temp folder next to the output and moved
# into place only once verified; the output is never one of the inputs (symlinks and hard links included).
# Exit status: 0 = written and verified; 1 = input problem, unreachable target or failed check, explained as
# "error: ... / fix: ...".
V="$1"; A="$2"; O="$3"; I="${4:--14}"; TP="${5:--1}"
err() { printf 'error: %s\n' "$1" >&2; [ -n "$2" ] && printf '  fix: %s\n' "$2" >&2; exit 1; }
warn() { printf 'warning: %s\n' "$1" >&2; }
calc() { awk "BEGIN { $1 }"; }
export LC_ALL=C   # awk, printf and ffmpeg filter args need '.' as the decimal point

[ -n "$O" ] || err "usage: sh mux.sh video.mp4 mix.wav out.mp4 [LUFS] [dBTP]"
for t in ffmpeg ffprobe; do
  command -v $t >/dev/null 2>&1 || err "$t is not on PATH" "install ffmpeg, which includes ffprobe (macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)"
done
[ -f "$V" ] || err "video not found: $V" "check the path"
[ -d "$(dirname "$O")" ] || err "output folder does not exist: $(dirname "$O")" "create it first"
case "$(basename "$O")" in ?*.?*) ;; *) err "output has no file extension, so ffmpeg cannot pick a container: $O" "name it e.g. final.mp4 or final.mov";; esac
{ [ "$V" -ef "$O" ] || [ "$A" -ef "$O" ]; } && err "output is one of the inputs (same file, maybe via a symlink or hard link): $O" \
  "write to a new file, e.g. final.mp4"

# the source video: its duration and packet count are what the output must keep
probe() { ffprobe -v error -select_streams "$1" -show_entries "$2" -of default=nw=1:nk=1 "$3" 2>/dev/null | head -1; }
VDUR=$(probe v:0 stream=duration "$V")
case "$VDUR" in ''|N/A) VDUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$V" 2>/dev/null);; esac
VPK=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of default=nw=1:nk=1 "$V" 2>/dev/null | head -1)
case "$VDUR$VPK" in *[!0-9.]*|'') err "cannot read a video stream from $V (duration '$VDUR', packets '$VPK')" "check that it is a video file ffmpeg can open";; esac
[ -n "$(probe a stream=index "$V")" ] && warn "$V has its own audio track; the output REPLACES it with $A (it is not mixed in). If it should stay (music, dialogue), extract it with: ffmpeg -i \"$V\" -vn -c:a pcm_s24le original.wav, pass original.wav to mix.py --music, remix, and mux again."

# a private folder next to the output (same filesystem, so the final mv is atomic; mktemp makes it 0700 with an
# unpredictable name, so nothing can be planted at the paths written inside it)
TMP=$(mktemp -d "$(dirname "$O")/.mux.XXXXXX") || err "cannot create a temp folder in $(dirname "$O")" "check that the folder is writable"
PART="$TMP/$(basename "$O")"
trap 'rm -rf "$TMP"' EXIT; trap 'exit 1' INT TERM HUP
sh "$(dirname "$0")/master.sh" "$A" "$TMP/master.wav" "$I" "$TP" >"$TMP/master.log" || exit 1
ADUR=$(probe a:0 stream=duration "$TMP/master.wav")
calc "d = $ADUR - $VDUR; exit !(d > .05 || d < -.05)" \
  && warn "the mix is ${ADUR}s but the video is ${VDUR}s; the audio is $(calc "exit !($ADUR < $VDUR)" && echo padded with silence || echo trimmed) to the video. Set \"dur\" in events.json to the video length."
ffmpeg -y -loglevel error -i "$V" -i "$TMP/master.wav" -map 0:v:0 -map 1:a:0 -c:v copy \
  -af "apad=whole_dur=$VDUR,atrim=end=$VDUR" -c:a aac -b:a 256k -movflags +faststart "$PART" >"$TMP/log" 2>&1 \
  || err "ffmpeg failed while writing $O: $(head -3 "$TMP/log" | tr '\n' ' ')" "check that $V has a video stream and that the folder for $O is writable"

# verify the finished file BEFORE it replaces anything at $O: complete video, audio as long as it, loudness, true peak
OPK=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of default=nw=1:nk=1 "$PART" 2>/dev/null | head -1)
ODUR=$(probe v:0 stream=duration "$PART"); OADUR=$(probe a:0 stream=duration "$PART")
case "$ODUR" in ''|N/A) ODUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$PART" 2>/dev/null);; esac
[ "$OPK" = "$VPK" ] && calc "d = $ODUR - $VDUR; exit !(d < .001 && d > -.001)" \
  || err "the output video does not match the source ($OPK packets / ${ODUR}s vs $VPK / ${VDUR}s); $O was not written" "rerun; if it repeats, report it with the video"
calc "d = $OADUR - $VDUR; exit !(d < .05 && d > -.05)" \
  || err "the output audio is ${OADUR}s but the video is ${VDUR}s; $O was not written" "rerun; if it repeats, report it with both inputs"
ffmpeg -hide_banner -nostats -i "$PART" -map 0:a:0 -af ebur128=peak=true:framelog=verbose -f null - >"$TMP/meter" 2>&1 \
  || err "the encoded file does not decode: $(grep -m1 -iE 'error|invalid' "$TMP/meter")" "rerun; if it persists, check disk space and the ffmpeg install"
M=$(awk '/Summary:/ { s = 1 } s && $1 == "I:" { i = $2 } s && $1 == "Peak:" { p = $2 } END { if (i != "" && p != "") print i, p }' "$TMP/meter")
[ -n "$M" ] || err "could not measure the encoded file's loudness" "rerun; if it persists, check the ffmpeg install"
set -- $M; EI=$1; EP=$2
calc "exit !($EP <= $TP + .05)" || {
  # codec overs are not proportional to level (a sine 0.5 dB quieter came out 0.8 dB over instead of 0.4), so the
  # suggestion takes 0.5 dB more than the overshoot
  SUG=$(calc "v = ($I - ($EP - ($TP)) - .5) * 10; f = int(v); if (f > v) f -= 1; printf \"%.1f\", f / 10")
  err "after AAC encoding the true peak is $EP dBTP, over the $TP limit (the codec added overs to a master that sat close to it); $O was not written" \
      "pass $SUG as the LUFS argument (the same mix, quieter by the overshoot plus 0.5 dB, as codec overs do not scale exactly with level), or lower the gain of the loudest events and remix"
}
calc "exit !($EI - ($I) <= .5 && ($I) - $EI <= .5)" \
  || err "after AAC encoding the loudness is $EI LUFS, more than 0.5 LU from the $I target; $O was not written" "rerun; if it repeats, report it with the mix"
mv -f "$PART" "$O" || err "could not move the result into place: $O" "check permissions on $O"
echo "$O"
sed 1d "$TMP/master.log"                                   # master.sh's gain and loudness line (its temp path dropped)
printf '  after AAC: %s LUFS, true peak %s dBTP; video %s packets / %ss, same as the source\n' "$EI" "$EP" "$OPK" "$ODUR"
