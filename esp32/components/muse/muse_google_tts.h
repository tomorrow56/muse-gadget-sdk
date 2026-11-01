/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * SPDX-License-Identifier: Apache-2.0
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* These three functions have one owner: the chat task. The worker owns its
 * copied text and response until done, including after cancellation. */
bool muse_google_tts_start(const char *text);
size_t muse_google_tts_read(uint8_t *out, size_t cap, bool *done, bool *ok);
void muse_google_tts_cancel(void);
/* Fixed sentence, for the voice task's idle-only test. Caller frees the MP3. */
uint8_t *muse_google_tts_fetch_test(size_t *len);
#ifdef __cplusplus
}
#endif
