#!/bin/bash
#
# Usage : speak.sh 192.168.1.121 "fr-FR" "bonjour le monde"
# prerequisites : 
# - install svoxpico to get pico2wave
# - install sox to get sox

[ $# -ne 3 ] && (echo "Usage : $(basename $0) <ip> <lang (fr-FR)> <texte>" ; exit 1)

# i18n
LANG=$2

# Text to speech
TEXT=$3

# FTP
HOST=$1
LOGIN=root
PASSWORD=dummy
PORT=21
TARGET_FILE=/home/hd1/test/tts.wav

# FILES
SOUND=/tmp/yi.wav
SRC_FILE=/tmp/yi2.wav

# Generate the wav
pico2wave -l "$LANG" -w $SOUND "$TEXT"
sox $SOUND $SRC_FILE speed 0.65 
#sox $SOUND $SRC_FILE tempo 0.65

# Upload the files
ftp -i -n $HOST $PORT << END_SCRIPT
quote USER $LOGIN
quote PASS $PASSWORD
pwd
bin
cd $(dirname $TARGET_FILE)
ls $(basename $TARGET_FILE)
delete $(basename $TARGET_FILE)
ls $(basename $TARGET_FILE)
put $SRC_FILE $(basename $TARGET_FILE)
quit
END_SCRIPT

# Play the file 
( sleep 1; echo "root"; sleep 1; echo "1234qwer"; sleep 1; echo "nohup /home/rmm $TARGET_FILE &" ; sleep 2 ) | telnet $HOST

