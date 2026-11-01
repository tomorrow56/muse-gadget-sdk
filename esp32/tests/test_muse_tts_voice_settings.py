# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: Apache-2.0
"""Persisted voice choice, boot defaults and failed flash commits."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from test_muse_ptt_ui import FAKE_HEADERS
ROOT=Path(__file__).resolve().parents[1]
class TTSVoiceSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        out=Path(cls.tmp.name)
        for f in (ROOT/'components/muse').glob('*.h'):shutil.copyfile(f,out/f.name)
        shutil.copyfile(ROOT/'components/muse/muse_settings.c',out/'muse_settings.c')
        shutil.copyfile(ROOT/'tests/muse_ptt_ui_fakes.h',out/'muse_ptt_ui_fakes.h')
        for name in FAKE_HEADERS:
            p=out/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_text('#include "muse_ptt_ui_fakes.h"\n')
        (out/'sdkconfig.h').write_text('#define CONFIG_MUSE_GOOGLE_TTS 1\n#define CONFIG_MUSE_GOOGLE_TTS_VOICE "ja-JP-Wavenet-B"\n#define CONFIG_MUSE_GOOGLE_TTS_LANGUAGE "ja-JP"\n#define CONFIG_MUSE_DEFAULT_VOLUME 70\n#define ESP_ERR_INVALID_ARG 0x102\n')
        (out/'test.c').write_text(r'''
#include <assert.h>
#include "muse_settings.c"
static uint8_t stored=255;static int sets,commits,set_error,commit_error;
esp_err_t nvs_flash_init(void){return ESP_OK;}
esp_err_t nvs_flash_erase(void){assert(0);return ESP_FAIL;}
esp_err_t nvs_open(const char *ns,nvs_open_mode_t m,nvs_handle_t *h){assert(!strcmp(ns,"muse"));*h=1;return ESP_OK;}
esp_err_t nvs_get_u8(nvs_handle_t h,const char *key,uint8_t *v){if(!strcmp(key,"tts_voice")){*v=stored;return ESP_OK;}return ESP_FAIL;}
esp_err_t nvs_get_u16(nvs_handle_t h,const char *k,uint16_t *v){return ESP_FAIL;}
esp_err_t nvs_get_str(nvs_handle_t h,const char *k,char *v,size_t *n){return ESP_FAIL;}
esp_err_t nvs_set_u8(nvs_handle_t h,const char *k,uint8_t v){assert(!strcmp(k,"tts_voice"));sets++;if(set_error)return ESP_FAIL;stored=v;return ESP_OK;}
esp_err_t nvs_commit(nvs_handle_t h){commits++;return commit_error?ESP_FAIL:ESP_OK;}
SemaphoreHandle_t xSemaphoreCreateMutex(void){return (void*)1;}
int xSemaphoreTake(SemaphoreHandle_t h,TickType_t t){return 1;}
int xSemaphoreGive(SemaphoreHandle_t h){return 1;}
int main(int argc,char **argv){
 assert(argc==2);assert(muse_settings_init()==ESP_OK);
 assert(!strcmp(muse_settings_tts_voice(),"ja-JP-Wavenet-B") && !sets && !commits);
 if(!strcmp(argv[1],"persist")){
  for(unsigned i=0;i<4;i++){
   assert(muse_settings_set_tts_voice(s_tts_voices[i])==ESP_OK);
   assert(stored==i && !strcmp(muse_settings_tts_voice(),s_tts_voices[i]));
   atomic_store(&s_tts_voice,255);assert(muse_settings_init()==ESP_OK);
   assert(!strcmp(muse_settings_tts_voice(),s_tts_voices[i]));
  }
  assert(sets==4 && commits==4);
 }else if(!strcmp(argv[1],"invalid")){
  assert(muse_settings_set_tts_voice(NULL)==ESP_ERR_INVALID_ARG);
  assert(muse_settings_set_tts_voice("ja-JP-Wavenet-E")==ESP_ERR_INVALID_ARG);
  assert(muse_settings_set_tts_voice("ja-JP-Wavenet-B\n>sleep=0")==ESP_ERR_INVALID_ARG);
  assert(!sets && !commits);stored=99;assert(muse_settings_init()==ESP_OK);
  assert(!strcmp(muse_settings_tts_voice(),"ja-JP-Wavenet-B"));
 }else if(!strcmp(argv[1],"fail")){
  set_error=1;assert(muse_settings_set_tts_voice("ja-JP-Wavenet-A")!=ESP_OK && !commits);
  assert(!strcmp(muse_settings_tts_voice(),"ja-JP-Wavenet-B"));
  set_error=0;commit_error=1;assert(muse_settings_set_tts_voice("ja-JP-Wavenet-D")!=ESP_OK);
  assert(!strcmp(muse_settings_tts_voice(),"ja-JP-Wavenet-B"));
 }else assert(0);
}
''')
        cls.binary=out/'test'
        cmd=shlex.split(os.environ.get('CC','cc'))+['-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-function','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-fsanitize=address,undefined','-include',str(ROOT/'tests/host_compat.h'),'-I',str(out),str(out/'test.c'),'-o',str(cls.binary)]
        subprocess.run(cmd,check=True)
    def run_case(self,name):subprocess.run([str(self.binary),name],check=True)
    def test_all_four_voices_survive_restart(self):self.run_case('persist')
    def test_invalid_commands_and_corrupt_nvs(self):self.run_case('invalid')
    def test_nvs_failures_do_not_publish_unsaved_voice(self):self.run_case('fail')
