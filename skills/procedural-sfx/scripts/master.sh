#!/bin/sh
# Master a mix for delivery: bring it to a loudness target with ONE static gain change, never touching the dynamics.
#   sh master.sh mix.wav out.wav [target_LUFS=-14] [true_peak_dBTP=-1]
# -14 LUFS suits YouTube/Spotify/social; -16 podcasts/Apple; -23 (EBU R128) or -24 (ATSC, with -2 dBTP) broadcast.
# Pass 1 measures integrated loudness and true peak with ffmpeg's ebur128 filter (peak=true), parsed from its
# "Summary:" block (I: ... LUFS, Peak: ... dBFS; one decimal, so 0.05 dB is allowed for rounding). ebur128 agreed with
# an independent BS.1770 implementation to 0.05 LU on test mixes, while loudnorm's own measurement read a sparse SFX
# mix ~0.6 LU loud. Pass 2 applies volume=<target - measured>dB and nothing else: loudnorm is never used, because
# its dynamic mode (which its "linear" mode falls back to when the target is out of reach) compresses and can pump.
# If that gain would push the true peak over the limit, nothing is written: the error names the loudest target that
# fits (lower the loudest events and remix to get closer). Output: 24-bit PCM wav at the input's sample rate
# (plays everywhere; the true-peak limit keeps samples under full scale, so fixed point cannot clip). It is rendered
# to a temp file next to the output, re-measured, and only then moved into place: a failed or interrupted run never
# leaves a partial file, and the input can never be written to (same-file check covers symlinks and hard links).
# The re-measured loudness must land within 0.15 LU of the target (0.1 plus the meter's rounding). Integrated loudness
# is gated, so a gain change can move blocks across the -70 LUFS / relative gates and the first gain can miss; the
# gain is then corrected from the original (never re-applied to the output) up to 3 more times before giving up.
# mux.sh runs this first, so video and audio-only deliveries share the same linear-only policy.
# Exit status: 0 = written and re-measured; 1 = input problem or unreachable target, explained as "error: ... / fix: ...".
A="$1"; O="$2"; I="${3:--14}"; TP="${4:--1}"
err() { printf 'error: %s\n' "$1" >&2; [ -n "$2" ] && printf '  fix: %s\n' "$2" >&2; exit 1; }
calc() { awk "BEGIN { $1 }"; }
export LC_ALL=C   # awk, printf and ffmpeg filter args need '.' as the decimal point (de_DE etc. would give 0,10dB)

[ -n "$O" ] || err "usage: sh master.sh mix.wav out.wav [LUFS] [dBTP]"
command -v ffmpeg >/dev/null 2>&1 || err "ffmpeg is not on PATH" "install it (macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)"
isnum() { printf '%s' "$1" | grep -Eq '^[+-]?[0-9]+([.][0-9]+)?$'; }
[ -f "$A" ] || err "audio not found: $A" "check the path; mix.py writes to its -o path"
[ -d "$(dirname "$O")" ] || err "output folder does not exist: $(dirname "$O")" "create it first"
[ "$A" -ef "$O" ] && err "output is the input file (same file, maybe via a symlink or hard link): $O" \
  "write to a new file, e.g. master.wav"
isnum "$I" && calc "exit !($I >= -70 && $I <= 0)" \
  || err "target loudness must be a number of LUFS in [-70, 0], got '$I'" "e.g. -14 (web), -16 (podcast), -23 (EBU R128)"
isnum "$TP" && calc "exit !($TP >= -9 && $TP <= 0)" \
  || err "true-peak limit must be a number of dBTP in [-9, 0], got '$TP'" "e.g. -1 (most platforms) or -2 (ATSC broadcast)"

LOG=$(mktemp); TMPO=""; trap 'rm -f "$LOG" ${TMPO:+"$TMPO"}' EXIT; trap 'exit 1' INT TERM HUP
measure() {   # measure FILE -> sets MI (integrated LUFS) and MTP (true peak dBTP)
  ffmpeg -hide_banner -nostats -i "$1" -af ebur128=peak=true:framelog=verbose -f null - >"$LOG" 2>&1 \
    || err "ffmpeg could not read $1: $(grep -m1 -iE 'error|invalid' "$LOG")" "check that it is a valid audio file"
  MI=$(sed -n '/Summary:/,$ s/^ *I: *\([^ ]*\) LUFS.*/\1/p' "$LOG" | tail -1)
  MTP=$(sed -n '/Summary:/,$ s/^ *Peak: *\([^ ]*\) dBFS.*/\1/p' "$LOG" | tail -1)
  LEN=$(grep -o 'time=[0-9:.]*' "$LOG" | tail -1)           # decoded length, to verify the render is complete
}

measure "$A"
# ebur128 reports -70.0 (its absolute gate) when no 400 ms block is loud enough to measure
isnum "$MI" && calc "exit !($MI > -70)" && isnum "$MTP" || err "loudness of $A could not be measured (got '$MI LUFS')" \
  "the mix is silent or shorter than ~0.4 s; check events and gains, or skip loudness mastering for a clip this short"
GAIN=$(calc "printf \"%.2f\", $I - ($MI)")
IN_I=$MI; IN_TP=$MTP; IN_LEN=$LEN
check_peak() {   # refuse a gain that would put the true peak over the limit, naming the loudest target that fits
  calc "exit !($IN_TP + .05 + $GAIN > $TP)" || return 0   # +0.05: the meter prints one decimal, so allow for its rounding
  # the loudest target that fits, rounded DOWN to 0.1 LU so passing it back is guaranteed to fit
  REACH=$(calc "v = ($I - $GAIN + $TP - $IN_TP - .05) * 10; f = int(v); if (f > v) f -= 1; printf \"%.1f\", f / 10")
  WHY="$A is at $IN_I LUFS with a true peak of $IN_TP dBTP; reaching $I LUFS needs $(calc "printf \"%+.2f\", $GAIN") dB of gain, which puts the true peak at $(calc "printf \"%+.2f\", $IN_TP + $GAIN") dBTP"
  if calc "exit !($IN_TP + $GAIN <= $TP)"; then   # only the rounding allowance tips it over: say so
    WHY="$WHY, or up to $(calc "printf \"%+.2f\", $IN_TP + $GAIN + .05") dBTP since the meter prints one decimal (limit $TP, so it is checked against $(calc "printf \"%.2f\", $TP - .05"))."
  else WHY="$WHY (limit $TP)."; fi
  calc "exit !($REACH < -70)" && err "$WHY No target above -70 LUFS fits: the loudest peaks dwarf everything else." \
    "lower the gain of the loudest events in events.json (or raise the quiet ones) and remix"
  err "$WHY The loudest target a clean gain change can reach is $REACH LUFS." \
      "accept that quieter target by passing $REACH as the LUFS argument, or lower the gain of the loudest events in events.json (their peaks limit the whole mix) and remix"
}
TMPO=$(mktemp "$(dirname "$O")/.master.XXXXXX") || err "cannot create a temp file in $(dirname "$O")" "check that the folder is writable"
TRY=1
while :; do
  check_peak
  ffmpeg -y -loglevel error -i "$A" -af "volume=${GAIN}dB" -c:a pcm_s24le -map_metadata -1 -fflags +bitexact -flags:a +bitexact \
    -f wav "$TMPO" >"$LOG" 2>&1 || err "ffmpeg failed while writing $O: $(head -3 "$LOG" | tr '\n' ' ')" "check that the folder for $O is writable and has space"
  measure "$TMPO"
  isnum "$MI" && isnum "$MTP" && calc "exit !($MTP <= $TP + .05)" && [ -n "$LEN" ] && [ "$LEN" = "$IN_LEN" ] \
    || err "the rendered file did not verify (I '$MI' LUFS, true peak '$MTP' dBTP, ${LEN:-no length} vs $IN_LEN); $O was not written" "rerun; if it repeats, report it with the input file"
  calc "exit !($MI - ($I) <= .15 && ($I) - $MI <= .15)" && break
  [ "$TRY" -ge 4 ] && err "after $TRY renders (gain corrected each time) the result still measures $MI LUFS, not $I (gain $GAIN dB); $O was not written" \
    "the target is so quiet that loudness gating keeps shifting; pick a target nearer $IN_I LUFS"
  GAIN=$(calc "printf \"%.2f\", $GAIN + ($I) - ($MI)"); TRY=$((TRY + 1))
done
chmod "$(printf '%o' $((0666 & ~0$(umask))))" "$TMPO"   # mktemp makes it 0600; give it normal permissions
mv -f "$TMPO" "$O" || err "could not move the result into place: $O" "check permissions on $O"
TMPO=""
echo "$O"
echo "  gain $(calc "printf \"%+.2f\", $GAIN") dB (linear only): $IN_I -> $MI LUFS (target $I), true peak $IN_TP -> $MTP dBTP (limit $TP)$([ "$TRY" -gt 1 ] && echo "; gain corrected $((TRY - 1))x for loudness gating")"
