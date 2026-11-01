# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: Apache-2.0
"""Production HTTPS/JSON/job ownership with deterministic HTTP and RTOS fakes."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JSON = Path(os.environ.get("CJSON_SOURCE_DIR", ROOT / "managed_components/espressif__cjson/cJSON"))

class GoogleTTS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name)
        fake = r'''#pragma once
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <algorithm>
#include <cassert>
#include "cJSON.h"
#define CONFIG_MUSE_GOOGLE_TTS_API_KEY "test-only-key"
#define CONFIG_MUSE_GOOGLE_TTS_LANGUAGE "ja-JP"
#define CONFIG_MUSE_GOOGLE_TTS_VOICE "ja-JP-Wavenet-B"
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define pdPASS 1
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM -2
#define HTTP_METHOD_POST 1
using esp_err_t = int;
static void log_fake(const char *, const char *, ...) {}
#define ESP_LOGI(...) log_fake(__VA_ARGS__)
#define ESP_LOGW(...) log_fake(__VA_ARGS__)
static const char *esp_err_to_name(int) { return "fake"; }
static int64_t clock_us;
static int64_t esp_timer_get_time() { return clock_us; }
static void *heap_caps_malloc(size_t n, int) { return malloc(n); }
static int esp_crt_bundle_attach(void *) { return 0; }
struct esp_http_client_config_t {
 const char *url; int method, timeout_ms, buffer_size, buffer_size_tx;
 int (*crt_bundle_attach)(void *); bool disable_auto_redirect;
};
using esp_http_client_handle_t = void *;
static std::string response, posted, key;
static size_t offset;
static int http_status = 200, fragment = 7, write_fragment = 3;
static bool read_error, truncated, create_fail, task_fail;
static int64_t advance;
static void (*task_body)(void *);
static void *task_arg;
static esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *cfg) {
 assert(!strcmp(cfg->url, "https://texttospeech.googleapis.com/v1/text:synthesize"));
 assert(cfg->disable_auto_redirect && cfg->crt_bundle_attach);
 offset = 0; posted.clear(); return create_fail ? nullptr : (void *)1;
}
static int esp_http_client_set_header(void *, const char *name, const char *value) {
 if (!strcmp(name,"X-Goog-Api-Key")) key=value;
 return 0;
}
static int esp_http_client_open(void *, int) { return 0; }
static int esp_http_client_write(void *, const char *p, int n) {
 n=std::min(n,write_fragment); if (n>0) posted.append(p,n); return n;
}
static int64_t esp_http_client_fetch_headers(void *) { return response.size(); }
static int esp_http_client_get_status_code(void *) { return http_status; }
static bool esp_http_client_is_complete_data_received(void *) { return offset==response.size() && !truncated; }
static int esp_http_client_read(void *, char *p, int n) {
 clock_us+=advance;
 if (read_error) return -1;
 n=std::min({n,fragment,(int)(response.size()-offset)});
 memcpy(p,response.data()+offset,n);offset+=n;return n;
}
static void esp_http_client_close(void *) {}
static void esp_http_client_cleanup(void *) {}
/* Fake only the external codec; JSON validation, bounds and ownership below
 * execute unchanged production code. Mbed TLS supplies real base64 on device. */
static int mbedtls_base64_decode(uint8_t *p,size_t cap,size_t *n,const uint8_t *s,size_t len) {
 if (cap<3 || len!=4 || memcmp(s,"SUQz",4)) return -1;
 memcpy(p,"ID3",3);*n=3;return 0;
}
static int xTaskCreatePinnedToCoreWithCaps(void (*body)(void *),const char *,int,void *arg,int,void *,int,int) {
 task_body=body;task_arg=arg;return task_fail ? 0 : 1;
}
static void vTaskDeleteWithCaps(void *) {}
'''
        (out / "fake.h").write_text(fake)
        for name in ["sdkconfig.h","esp_crt_bundle.h","esp_heap_caps.h","esp_http_client.h","esp_log.h","esp_timer.h","freertos/FreeRTOS.h","freertos/task.h","freertos/idf_additions.h","mbedtls/base64.h"]:
            p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "fake.h"\n')
        harness=r'''
#include "fake.h"
#include "muse_google_tts.cpp"
static void reset() {
 muse_google_tts_cancel();
 response=R"({"audioContent":"SUQz"})";
 http_status=200;fragment=7;write_fragment=3;
 read_error=truncated=create_fail=task_fail=false;clock_us=advance=0;
}
int main(int argc,char **argv) {
 assert(argc==2);reset();std::string test=argv[1];size_t len;
 if(test=="request") {
  auto *p=fetch("日本語\n\"返答\"",nullptr,&len);
  assert(p && len==3 && !memcmp(p,"ID3",3));free(p);
  assert(key=="test-only-key");cJSON *j=cJSON_Parse(posted.c_str());assert(j);
  assert(!strcmp(cJSON_GetObjectItem(cJSON_GetObjectItem(j,"input"),"text")->valuestring,"日本語\n\"返答\""));
  assert(!strcmp(cJSON_GetObjectItem(cJSON_GetObjectItem(j,"voice"),"name")->valuestring,"ja-JP-Wavenet-B"));cJSON_Delete(j);
 } else if(test=="bad_response") {
  for (const char *s : {"{}","[]",R"({"audioContent":4})",R"({"audioContent":""})",R"({"audioContent":"!!!!"})",R"({"audioContent":"SUQz"} junk)"}) {
   response=s;assert(!fetch("text",nullptr,&len) && len==0);
  }
  response=std::string("{}\0junk",7);assert(!fetch("text",nullptr,&len));
 } else if(test=="transport") {
  for(int status : {301,401,403,429,500}) {http_status=status;assert(!fetch("text",nullptr,&len));assert(offset==0);}
  http_status=200;read_error=true;assert(!fetch("text",nullptr,&len));
  read_error=false;truncated=true;assert(!fetch("text",nullptr,&len));
  truncated=false;write_fragment=0;assert(!fetch("text",nullptr,&len));
  write_fragment=3;response.assign(RESPONSE_MAX+1,'x');assert(!fetch("text",nullptr,&len));assert(offset==0);
 } else if(test=="deadline") {
  advance=DEADLINE_US;fragment=1;assert(!fetch("text",nullptr,&len));
  std::atomic<bool> cancel{true};reset();assert(!fetch("text",&cancel,&len));assert(posted.empty());
 } else if(test=="ownership") {
  assert(muse_google_tts_start("old"));
  muse_google_tts_cancel();assert(s_job && !s_job->done);
  assert(!muse_google_tts_start("new"));task_body(task_arg);
  assert(muse_google_tts_start("new"));task_body(task_arg);
  uint8_t bytes[4]={};bool done,ok;
  assert(muse_google_tts_read(bytes,1,&done,&ok)==1 && !done && ok && bytes[0]=='I');
  assert(muse_google_tts_read(bytes+1,3,&done,&ok)==2 && done && ok && !s_job);
  assert(!memcmp(bytes,"ID3",3));
 } else if(test=="allocation") {
  task_fail=true;assert(!muse_google_tts_start("text") && !s_job);
  task_fail=false;create_fail=true;assert(muse_google_tts_start("text"));task_body(task_arg);
  uint8_t bytes[4];bool done,ok;assert(!muse_google_tts_read(bytes,4,&done,&ok) && done && !ok && !s_job);
  assert(!muse_google_tts_start(""));std::string long_text(TEXT_MAX,'x');assert(!muse_google_tts_start(long_text.c_str()));
 } else { assert(false); }
 muse_google_tts_cancel();assert(!s_job);
}
'''
        (out / "test.cpp").write_text(harness)
        cc=shlex.split(os.environ.get("CC","cc"));cxx=shlex.split(os.environ.get("CXX","c++"))
        subprocess.run(cc+["-I",str(JSON),"-c",str(JSON/"cJSON.c"),"-o",str(out/"json.o")],check=True)
        cls.binary=out/"test"
        subprocess.run(cxx+["-std=c++17","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(out),"-I",str(JSON),"-I",str(ROOT/"components/muse"),str(out/"test.cpp"),str(out/"json.o"),"-o",str(cls.binary)],check=True)

    def run_case(self, name):
        subprocess.run([str(self.binary), name], check=True)
    def test_unicode_request_and_fragmented_response(self): self.run_case("request")
    def test_invalid_response_retains_text_fallback(self): self.run_case("bad_response")
    def test_http_errors_truncation_and_limits(self): self.run_case("transport")
    def test_deadline_and_cancellation(self): self.run_case("deadline")
    def test_cancelled_worker_cannot_write_new_turn(self): self.run_case("ownership")
    def test_task_and_transport_allocation_failures(self): self.run_case("allocation")
