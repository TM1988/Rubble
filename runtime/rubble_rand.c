/*
 * Rubble rand module — rubble_rand.c
 *
 * Rubble API:
 *   rand.int(min, max)   -> unit      -- random integer in [min, max]
 *   rand.decimal()       -> decimal   -- random double in [0.0, 1.0)
 *   rand.seed(n)                      -- seed the RNG
 */

#define _CRT_SECURE_NO_WARNINGS
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

/* Use a simple xorshift64 for decent randomness without OS dependencies */
static uint64_t _rng_state = 0;

static void _rng_ensure_seeded(void) {
    if (_rng_state == 0) {
        _rng_state = (uint64_t)time(NULL) ^ 0xdeadbeefcafeULL;
        if (_rng_state == 0) _rng_state = 1;
    }
}

static uint64_t _xorshift64(void) {
    _rng_state ^= _rng_state << 13;
    _rng_state ^= _rng_state >> 7;
    _rng_state ^= _rng_state << 17;
    return _rng_state;
}

void rubble_rand_seed(int64_t seed) {
    _rng_state = (uint64_t)seed;
    if (_rng_state == 0) _rng_state = 1;
}

int64_t rubble_rand_int(int64_t min, int64_t max) {
    _rng_ensure_seeded();
    if (min > max) {
        int64_t tmp = min; min = max; max = tmp;
    }
    int64_t range = max - min + 1;
    if (range <= 0) return min;
    return min + (int64_t)(_xorshift64() % (uint64_t)range);
}

double rubble_rand_decimal(void) {
    _rng_ensure_seeded();
    return (double)(_xorshift64() >> 11) / (double)(UINT64_C(1) << 53);
}
