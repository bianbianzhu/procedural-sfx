#!/bin/sh
# Put a mix under a video, loudness-mastered with a single linear gain change (master.sh does that part).
#   sh mux.sh video.mp4 mix.wav out.mp4 [target_LUFS=-14] [true_peak_dBTP=-1]
# -14 LUFS suits YouTube/Spotify/social; -16 podcasts/Apple; -23 (EBU R128) or -24 (ATSC, with -2 dBTP) broadcast.
# master.sh measures, refuses a target that would need more gain than the true-peak limit allows (and names the
# loudest reachable one), and writes the gained wav; this script copies the video stream and encodes that audio to
# AAC 256k.
# The video is the timeline: every video packet is copied (no -shortest, which drops the last frames of a copied
# B-frame stream when the audio ends at the same instant), and the mix is padded with silence or trimmed to the
# video's span BEFORE mastering, so the loudness target applies to the audio that ships (a warning says when the mix
# length differs). The video's span comes from its packet timestamps, not from container durations. The mix REPLACES any audio the video already has;
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
isnum() { printf '%s' "$1" | grep -Eq '^[+-]?[0-9]+([.][0-9]+)?$'; }
export LC_ALL=C   # awk, printf and ffmpeg filter args need '.' as the decimal point

[ -n "$O" ] || err "usage: sh mux.sh video.mp4 mix.wav out.mp4 [LUFS] [dBTP]"
for t in ffmpeg ffprobe; do
  command -v $t >/dev/null 2>&1 || err "$t is not on PATH" "install ffmpeg, which includes ffprobe (macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)"
done
[ -f "$V" ] || err "video not found: $V" "check the path"
[ -d "$(dirname "$O")" ] || err "output folder does not exist: $(dirname "$O")" "create it first"
case "$(basename "$O")" in
  ?*.[mM][pP]4|?*.[mM]4[vV]|?*.[mM][oO][vV]|?*.[mM][kK][vV]) ;;
  *) err "output must be .mp4, .m4v, .mov or .mkv (AAC audio does not go in other containers such as .webm): $O" "name it e.g. final.mp4";;
esac
{ [ "$V" -ef "$O" ] || [ "$A" -ef "$O" ]; } && err "output is one of the inputs (same file, maybe via a symlink or hard link): $O" \
  "write to a new file, e.g. final.mp4"

# a stream's packets -> "count start end": end = the latest pts + packet duration. The video's length for fitting the
# audio is its stream duration where the container has one (.mp4/.mov: it honours an edit list, which can hide
# packets kept only for decoding), else this packet span (.mkv has no per-stream duration). The container duration
# is never used: it can be a longer original audio track, or include codec delay.
span() {
  ffprobe -v error -select_streams "$1" -show_entries packet=pts_time,duration_time -of csv=p=0 "$2" 2>/dev/null |
    awk -F, '$1 ~ /^-?[0-9.]+$/ { n++; p = $1 + 0; d = ($2 ~ /^[0-9.]+$/) ? $2 + 0 : 0
      if (n == 1 || p < lo) lo = p; if (n == 1 || p > hi) hi = p; if (n == 1 || p + d > e) e = p + d }
      END { if (!n) exit; if (e <= hi && n > 1) e = hi + (hi - lo) / (n - 1); printf "%d %.6f %.6f\n", n, lo, e }'
}
SV=$(span v:0 "$V"); [ -n "$SV" ] || err "cannot read a video stream from $V" "check that it is a video file ffmpeg can open"
set -- $SV; VPK=$1; VSPAN=$(calc "printf \"%.6f\", $3 - $2")
VDUR=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 "$V" 2>/dev/null | head -1)
isnum "$VDUR" && calc "exit !($VDUR > 0)" || VDUR=$VSPAN
calc "exit !($VDUR >= .4)" || err "the video is only ${VDUR}s; loudness (and so mastering) needs at least 0.4 s" \
  "for a clip this short mux it yourself: ffmpeg -i video -i mix.wav -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 256k out.mp4"
ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$V" 2>/dev/null | grep -q . \
  && warn "$V has its own audio track; the output REPLACES it with $A (it is not mixed in). If it should stay (music, dialogue), extract it with: ffmpeg -i \"$V\" -vn -c:a pcm_s24le original.wav, pass original.wav to mix.py --music, remix, and mux again."
ffmpeg -hide_banner -h filter=apad 2>/dev/null | grep -q whole_dur \
  || err "this ffmpeg is too old (its apad filter has no whole_dur option)" "install ffmpeg 4.2 or newer"

# a private folder next to the output (same filesystem, so the final mv is atomic; mktemp makes it 0700 with an
# unpredictable name, so nothing can be planted at the paths written inside it)
TMP=$(mktemp -d "$(dirname "$O")/.mux.XXXXXX") || err "cannot create a temp folder in $(dirname "$O")" "check that the folder is writable"
PART="$TMP/$(basename "$O")"; FIT="$TMP/fitted.wav"
trap 'rm -rf "$TMP"' EXIT; trap 'exit 1' INT TERM HUP
# fit the mix to the video FIRST, so the loudness target applies to exactly the audio that ships (32-bit float keeps
# it lossless); then master that
ADUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$A" 2>/dev/null)
isnum "$ADUR" || err "cannot read the mix: $A" "check that it is an audio file (mix.py writes a wav)"
calc "d = $ADUR - $VDUR; exit !(d > .05 || d < -.05)" \
  && warn "the mix is ${ADUR}s but the video is ${VDUR}s; the audio is $(calc "exit !($ADUR < $VDUR)" && echo padded with silence || echo trimmed) to the video before mastering. Set \"dur\" in events.json to the video length."
ffmpeg -y -loglevel error -i "$A" -af "apad=whole_dur=$VDUR,atrim=end=$VDUR" -c:a pcm_f32le -f wav "$FIT" >"$TMP/log" 2>&1 \
  || err "ffmpeg could not fit $A to the video length: $(head -3 "$TMP/log" | tr '\n' ' ')" "check that it is a valid audio file"
sh "$(dirname "$0")/master.sh" "$FIT" "$TMP/master.wav" "$I" "$TP" >"$TMP/master.log" 2>"$TMP/master.err" || {
  # name the user's mix in master.sh's message, not the temp copy it was given
  awk -v f="$FIT" -v r="$A (fitted to the video's ${VDUR}s)" '{ while (i = index($0, f)) $0 = substr($0, 1, i - 1) r substr($0, i + length(f)); print }' "$TMP/master.err" >&2
  exit 1
}
ffmpeg -y -loglevel error -i "$V" -i "$TMP/master.wav" -map 0:v:0 -map 1:a:0 -c:v copy \
  -c:a aac -b:a 256k -movflags +faststart "$PART" >"$TMP/log" 2>&1 || {
  grep -q 'Could not find tag for codec\|not currently supported in container' "$TMP/log" \
    && err "the $(basename "$O" | sed 's/.*\.//') container cannot hold this video codec or AAC: $(head -1 "$TMP/log")" \
           "use an .mp4/.mov output for H.264/HEVC video, or .mkv for anything else (e.g. VP8/VP9 from a .webm)"
  err "ffmpeg failed while writing $O: $(head -3 "$TMP/log" | tr '\n' ' ')" "check that $V has a video stream and that the folder for $O is writable"
}

# verify the finished file BEFORE it replaces anything at $O: every video packet, the same video span (to half a frame:
# containers round timestamps, .mkv to 1 ms), audio ending with the video, loudness, true peak
SO=$(span v:0 "$PART"); set -- ${SO:-0 0 0}; OPK=$1; OST=$2; ODUR=$(calc "printf \"%.6f\", $3 - $2")
TOL=$(calc "t = $VSPAN / $VPK / 2; if (t < .002) t = .002; print t")
[ "$OPK" = "$VPK" ] && calc "d = $ODUR - $VSPAN; exit !(d <= $TOL && d >= -$TOL)" \
  || err "the output video does not match the source ($OPK packets spanning ${ODUR}s vs $VPK spanning ${VSPAN}s); $O was not written" "report it with the video and the ffmpeg version (this should not happen)"
SA=$(span a:0 "$PART"); set -- ${SA:-0 0 x}; AEND=$3
isnum "$AEND" && calc "d = $AEND - $VDUR; exit !(d < .05 && d > -.05)" \
  || err "the output audio ends at ${AEND:-?}s but the video spans ${VDUR}s; $O was not written" "report it with both inputs and the ffmpeg version (this should not happen)"
ffmpeg -hide_banner -nostats -i "$PART" -map 0:a:0 -af ebur128=peak=true:framelog=verbose -f null - >"$TMP/meter" 2>&1 \
  || err "the encoded file does not decode: $(grep -m1 -iE 'error|invalid' "$TMP/meter")" "rerun; if it persists, check disk space and the ffmpeg install"
M=$(awk '/Summary:/ { s = 1 } s && $1 == "I:" { i = $2 } s && $1 == "Peak:" { p = $2 } END { if (i != "" && p != "") print i, p }' "$TMP/meter")
[ -n "$M" ] || err "could not measure the encoded file's loudness" "rerun; if it persists, check the ffmpeg install"
set -- $M; EI=$1; EP=$2
calc "exit !($EP <= $TP + .05)" || {
  # codec overs are not proportional to level (a sine 0.5 dB quieter came out 0.8 dB over instead of 0.4), so the
  # suggestion takes 0.5 dB more than the overshoot; it is a candidate, re-encoded and verified like any other run
  SUG=$(calc "v = ($I - ($EP - ($TP)) - .5) * 10; f = int(v); if (f > v) f -= 1; printf \"%.1f\", f / 10")
  err "after AAC encoding the true peak is $EP dBTP, over the $TP limit (the codec added overs to a master that sat close to it); $O was not written" \
      "try $SUG as the LUFS argument (the same mix, quieter by the overshoot plus 0.5 dB; codec overs do not scale exactly with level, so it is verified again and may need one more step), or lower the gain of the loudest events and remix"
}
calc "exit !($EI - ($I) <= .5 && ($I) - $EI <= .5)" \
  || err "after AAC encoding the loudness is $EI LUFS, more than 0.5 LU from the $I target; $O was not written" "report it with the mix and the ffmpeg version (AAC drift is normally under 0.2 LU)"
mv -f "$PART" "$O" || err "could not move the result into place: $O" "check permissions on $O"
echo "$O"
sed 1d "$TMP/master.log"                                   # master.sh's gain and loudness line (its temp path dropped)
printf '  after AAC: %s LUFS, true peak %s dBTP; video %s packets (as the source), audio fitted to %ss\n' "$EI" "$EP" "$OPK" "$VDUR"
