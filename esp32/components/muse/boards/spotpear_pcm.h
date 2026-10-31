/* SpotPear: streaming 16 kHz -> 24 kHz linear interpolation, one input
 * sample of latency. State persists across DMA writes. */
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    int16_t previous;
    bool initialized;
    bool odd;
} spotpear_resampler_t;

static inline int spotpear_resample(spotpear_resampler_t *s, int16_t sample, int32_t out[2])
{
    if (!s->initialized) {
        s->previous = sample;
        s->initialized = true;
    }
    int32_t a = s->previous, delta = (int32_t)sample - a;
    int n;
    if (!s->odd) {
        out[0] = a * 65536;
        out[1] = (a + delta * 2 / 3) * 65536;
        n = 2;
    } else {
        out[0] = (a + delta / 3) * 65536;
        n = 1;
    }
    s->odd = !s->odd;
    s->previous = sample;
    return n;
}
