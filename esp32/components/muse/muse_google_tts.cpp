/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * SPDX-License-Identifier: Apache-2.0
 */

#include "muse_google_tts.h"
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <new>
#include "sdkconfig.h"
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "mbedtls/base64.h"

static const char *TAG = "muse_google_tts";
static constexpr size_t AUDIO_MAX = 512 * 1024;
static constexpr size_t RESPONSE_MAX = (AUDIO_MAX + 2) / 3 * 4 + 4096;
static constexpr size_t TEXT_MAX = 1024;
static constexpr int64_t DEADLINE_US = 45 * 1000000LL;
struct response_t {
    uint8_t *buf;
    size_t len;
    const std::atomic<bool> *cancelled;
    int64_t deadline;
};
static bool cancelled(const response_t &r)
{
    return (r.cancelled && r.cancelled->load()) || esp_timer_get_time() >= r.deadline;
}
/* Decode into the response buffer, separate from cJSON's owned string. No
 * second MP3 allocation, and no partially downloaded speech is published. */
static bool decode_response(uint8_t *buf, size_t len, size_t *audio_len)
{
    *audio_len = 0;
    if (memchr(buf, 0, len)) return false;
    buf[len] = 0;
    const char *end = nullptr;
    cJSON *root = cJSON_ParseWithLengthOpts(reinterpret_cast<char *>(buf), len + 1, &end, true);
    const cJSON *audio = cJSON_GetObjectItemCaseSensitive(root, "audioContent");
    bool ok = cJSON_IsObject(root) && cJSON_IsString(audio) && audio->valuestring[0];
    if (ok) {
        size_t encoded_len = strlen(audio->valuestring);
        ok = encoded_len % 4 == 0 &&
             mbedtls_base64_decode(buf, AUDIO_MAX, audio_len,
                                  reinterpret_cast<const uint8_t *>(audio->valuestring), encoded_len) == 0 &&
             *audio_len > 0 && *audio_len <= AUDIO_MAX;
    }
    cJSON_Delete(root);
    return ok;
}

static uint8_t *fetch(const char *text, const std::atomic<bool> *cancel, size_t *len)
{
    *len = 0;
    if (!CONFIG_MUSE_GOOGLE_TTS_API_KEY[0] || !text || !text[0] || strlen(text) >= TEXT_MAX) {
        return nullptr;
    }
    response_t response = {};
    response.buf = static_cast<uint8_t *>(heap_caps_malloc(RESPONSE_MAX + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    response.cancelled = cancel;
    response.deadline = esp_timer_get_time() + DEADLINE_US;
    cJSON *root = cJSON_CreateObject();
    cJSON *input = cJSON_AddObjectToObject(root, "input");
    cJSON *voice = cJSON_AddObjectToObject(root, "voice");
    cJSON *config = cJSON_AddObjectToObject(root, "audioConfig");
    bool built = root && input && voice && config &&
        cJSON_AddStringToObject(input, "text", text) &&
        cJSON_AddStringToObject(voice, "languageCode", CONFIG_MUSE_GOOGLE_TTS_LANGUAGE) &&
        cJSON_AddStringToObject(voice, "name", CONFIG_MUSE_GOOGLE_TTS_VOICE) &&
        cJSON_AddStringToObject(config, "audioEncoding", "MP3") &&
        cJSON_AddNumberToObject(config, "sampleRateHertz", 16000);
    char *body = built ? cJSON_PrintUnformatted(root) : nullptr;
    cJSON_Delete(root);
    esp_http_client_config_t cfg = {};
    cfg.url = "https://texttospeech.googleapis.com/v1/text:synthesize";
    cfg.method = HTTP_METHOD_POST;
    cfg.timeout_ms = 15000;
    cfg.buffer_size = 4096;
    cfg.buffer_size_tx = 4096;
    cfg.crt_bundle_attach = esp_crt_bundle_attach;
    cfg.disable_auto_redirect = true;
    esp_http_client_handle_t client = response.buf && body ? esp_http_client_init(&cfg) : nullptr;
    esp_err_t error = ESP_ERR_NO_MEM;
    int status = 0;
    if (client) {
        error = esp_http_client_set_header(client, "Content-Type", "application/json; charset=utf-8");
        if (error == ESP_OK) error = esp_http_client_set_header(client, "X-Goog-Api-Key", CONFIG_MUSE_GOOGLE_TTS_API_KEY);
        size_t body_len = strlen(body), sent = 0;
        if (error == ESP_OK && !cancelled(response)) error = esp_http_client_open(client, body_len);
        while (error == ESP_OK && sent < body_len && !cancelled(response)) {
            int n = esp_http_client_write(client, body + sent, body_len - sent);
            if (n <= 0) error = ESP_FAIL;
            else sent += n;
        }
        int64_t content_length = -1;
        if (error == ESP_OK && !cancelled(response)) content_length = esp_http_client_fetch_headers(client);
        status = esp_http_client_get_status_code(client);
        if (error == ESP_OK && (content_length < 0 || content_length > (int64_t)RESPONSE_MAX || status != 200)) error = ESP_FAIL;
        while (error == ESP_OK && !cancelled(response) && !esp_http_client_is_complete_data_received(client)) {
            size_t room = RESPONSE_MAX - response.len;
            if (!room) { error = ESP_FAIL; break; }
            int n = esp_http_client_read(client, reinterpret_cast<char *>(response.buf + response.len),
                                         room < 4096 ? room : 4096);
            if (n < 0) error = ESP_FAIL;
            else if (n > 0) response.len += n;
            else if (!esp_http_client_is_complete_data_received(client)) error = ESP_FAIL;
        }
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
    }
    cJSON_free(body);
    bool ok = error == ESP_OK && status == 200 && !cancelled(response) && decode_response(response.buf, response.len, len);
    if (!ok) {
        /* Never print request headers, response bodies, the key or reply text. */
        ESP_LOGW(TAG, "synthesis failed: HTTP %d, transport %s, cancelled %d", status,
                 esp_err_to_name(error), cancelled(response));
        free(response.buf);
        *len = 0;
        return nullptr;
    }
    ESP_LOGI(TAG, "synthesized %u MP3 bytes (%s)", (unsigned)*len, CONFIG_MUSE_GOOGLE_TTS_VOICE);
    return response.buf;
}

struct job_t {
    char text[TEXT_MAX];
    std::atomic<bool> cancel{false};
    std::atomic<bool> done{false};
    uint8_t *audio = nullptr;
    size_t len = 0, pos = 0;
};
/* Only the chat task touches this pointer. Workers only touch their job. */
static job_t *s_job;
static void release_job(void)
{
    free(s_job->audio);
    delete s_job;
    s_job = nullptr;
}
void muse_google_tts_cancel(void)
{
    if (s_job) {
        s_job->cancel.store(true);
        if (s_job->done.load(std::memory_order_acquire)) release_job();
    }
}
bool muse_google_tts_start(const char *text)
{
    muse_google_tts_cancel();
    if (s_job || !text || !*text || strlen(text) >= TEXT_MAX || !CONFIG_MUSE_GOOGLE_TTS_API_KEY[0]) {
        return false;
    }
    s_job = new (std::nothrow) job_t;
    if (!s_job) return false;
    memcpy(s_job->text, text, strlen(text) + 1);
    auto body = [](void *arg) {
        auto *job = static_cast<job_t *>(arg);
        job->audio = fetch(job->text, &job->cancel, &job->len);
        if (job->cancel.load()) {
            free(job->audio);
            job->audio = nullptr;
        }
        job->done.store(true, std::memory_order_release);
        vTaskDeleteWithCaps(nullptr);
    };
    if (xTaskCreatePinnedToCoreWithCaps(body, "google_tts", 24 * 1024, s_job, 4, nullptr, 0,
                                      MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) != pdPASS) {
        release_job();
        return false;
    }
    return true;
}
size_t muse_google_tts_read(uint8_t *out, size_t cap, bool *done, bool *ok)
{
    *done = *ok = false;
    if (!s_job || !s_job->done.load(std::memory_order_acquire)) return 0;
    *ok = s_job->audio && !s_job->cancel.load();
    size_t n = *ok ? s_job->len - s_job->pos : 0;
    if (n > cap) n = cap;
    if (n) memcpy(out, s_job->audio + s_job->pos, n);
    s_job->pos += n;
    *done = !*ok || s_job->pos == s_job->len;
    if (*done) release_job();
    return n;
}
uint8_t *muse_google_tts_fetch_test(size_t *len)
{
    return fetch("こんにちは。ミューズの音声読み上げテストです。", nullptr, len);
}
