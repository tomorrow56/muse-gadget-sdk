# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: Apache-2.0
"""Enabled TTS adapter: mute, backpressure, fallback and turn cancellation."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]

class GoogleTTSTurn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        out=Path(cls.tmp.name)
        source=(ROOT/"components/muse/muse_chat_session.cpp").read_text()
        def function(name):
            begin=source.index("static void "+name+"(void)")
            return source[begin:source.index("\n}\n",begin)+3]
        harness=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <algorithm>
#define CONFIG_MUSE_GOOGLE_TTS 1
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define TEXT_MAX 32
#define MP3_BUF 8
#define MIC_RATE 16000
#define TEXT_CHARS_PER_S 16
#define TTS_QUEUED 1
#define TTS_ACTIVE 2
#define P_IDLE 0
#define M_MP3 1
struct msg_t { int tts;uint32_t pcm_start,pcm_frames;size_t len;char id[4]; };
struct {
 int nmsgs=1,tts_msg=-1,kbps=0,down_rate=0,dec=0,phase=1,dict_id=1,chat_id=2;
 bool silent=false,mp3_ended=false;uint32_t pcm_out=0;size_t mp3_len=0;
 char *texts;msg_t msgs[1];uint8_t mp3[MP3_BUF+1];
} s_turn;
static bool speaker=true,accepted=true,ready=false,success=true,cancelled=false;
static int volume=70,started=0,shown=0;static size_t remaining=12;
static bool muse_settings_speaker_on(){return speaker;}
static int muse_settings_volume(){return volume;}
static bool muse_google_tts_start(const char *text){if(text && *text && accepted){started++;return true;}return false;}
static void muse_google_tts_cancel(){cancelled=true;}
static void turn_reset_streams(){}
static void mark(int){}
static void show_reply_start(msg_t &){shown++;}
static void mp3dec_init(int *n){(*n)++;}
static size_t muse_google_tts_read(uint8_t *out,size_t cap,bool *done,bool *ok){
 *done=*ok=false;if(!ready)return 0;
 *ok=success;if(!success){*done=true;return 0;}
 size_t n=std::min(cap,remaining);memset(out,0x45,n);remaining-=n;*done=!remaining;return n;
}
'''+function("start_tts")+function("pump_google_tts")+function("turn_finish")+r'''
int main(int argc,char **argv){
 assert(argc==2);s_turn.msgs[0].tts=TTS_QUEUED;char text[TEXT_MAX]="Japanese reply";
 s_turn.texts=text;s_turn.msgs[0].len=strlen(text);s_turn.mp3[MP3_BUF]=0x77;
 if(!strcmp(argv[1],"mute")){
  speaker=false;start_tts();assert(!started && shown==1 && s_turn.silent);
  speaker=true;volume=0;s_turn.tts_msg=-1;s_turn.msgs[0].tts=TTS_QUEUED;
  start_tts();assert(!started && shown==2 && s_turn.silent);
 }else if(!strcmp(argv[1],"fallback")){
  start_tts();assert(started==1 && !s_turn.silent && !s_turn.msgs[0].pcm_frames);
  pump_google_tts();assert(!s_turn.silent && !s_turn.mp3_len);
  ready=true;success=false;pump_google_tts();
  assert(s_turn.silent && s_turn.msgs[0].pcm_frames==strlen(text)*MIC_RATE/TEXT_CHARS_PER_S);
 }else if(!strcmp(argv[1],"backpressure")){
  start_tts();ready=true;pump_google_tts();assert(s_turn.mp3_len==MP3_BUF && !s_turn.mp3_ended);
  pump_google_tts();assert(s_turn.mp3_len==MP3_BUF && !s_turn.mp3_ended);
  s_turn.mp3_len=0;pump_google_tts();assert(s_turn.mp3_len==4 && s_turn.mp3_ended);
  assert(s_turn.mp3[MP3_BUF]==0x77);
 }else if(!strcmp(argv[1],"cancel")){
  start_tts();turn_finish();assert(cancelled && s_turn.tts_msg==-1 && !s_turn.mp3_len && s_turn.phase==P_IDLE);
  pump_google_tts();assert(!s_turn.mp3_len);
 }else{assert(false);}
}
'''
        (out/"test.cpp").write_text(harness);cls.binary=out/"test"
        subprocess.run(shlex.split(os.environ.get("CXX","c++"))+["-std=c++17","-Wall","-Wextra","-Werror","-fsanitize=address,undefined",str(out/"test.cpp"),"-o",str(cls.binary)],check=True)
    def test_mute_and_zero_volume_skip_google(self):subprocess.run([str(self.binary),"mute"],check=True)
    def test_failure_returns_to_reading_pace(self):subprocess.run([str(self.binary),"fallback"],check=True)
    def test_backpressure_does_not_drop_mp3_bytes(self):subprocess.run([str(self.binary),"backpressure"],check=True)
    def test_cancel_ends_audio_before_another_turn(self):subprocess.run([str(self.binary),"cancel"],check=True)
