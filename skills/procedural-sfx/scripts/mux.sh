#!/bin/sh
# Put a mix under a video with two-pass loudness normalisation.
#   sh mux.sh video.mp4 mix.wav out.mp4 [target_LUFS=-14] [true_peak_dBTP=-1.2]
# -14 LUFS suits YouTube/Spotify/social; use -16 for podcasts/Apple, -23 (EBU R128) or -24 (ATSC) for broadcast.
# Two passes: the first measures, the second corrects exactly (a single pass lands ~0.5 LU off).
set -e
V="$1"; A="$2"; O="$3"; I="${4:--14}"; TP="${5:--1.2}"
[ -n "$O" ] || { echo "usage: sh mux.sh video.mp4 mix.wav out.mp4 [LUFS] [dBTP]"; exit 1; }
J=$(ffmpeg -hide_banner -nostats -i "$A" -af loudnorm=I=$I:TP=$TP:LRA=11:print_format=json -f null - 2>&1 | sed -n '/{/,/}/p')
g() { echo "$J" | grep "\"$1\"" | sed 's/.*: "\(.*\)".*/\1/'; }
LN="loudnorm=I=$I:TP=$TP:LRA=11:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true"
ffmpeg -y -loglevel error -i "$V" -i "$A" \
  -filter_complex "[1:a]$LN,aresample=48000[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 256k -movflags +faststart -shortest "$O"
echo "$O"
ffmpeg -hide_banner -nostats -i "$O" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I|LRA|Peak):" | head -3
