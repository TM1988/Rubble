/*
 * Rubble time module — rubble_time.c
 *
 * Rubble API:
 *   time.now()              -> unit     Unix timestamp in seconds
 *   time.format(ts, fmt)    -> text     strftime-style formatting
 *   time.sleep(ms)          -> (maps to rubble_machinery_rest — no separate impl needed)
 *
 * Format specifiers (passed directly to strftime):
 *   %Y  year       %m  month (01-12)   %d  day (01-31)
 *   %H  hour(24h)  %M  minute          %S  second
 *   %A  weekday    %B  month name      %c  locale datetime
 */

#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int64_t rubble_time_now(void) {
    return (int64_t)time(NULL);
}

/* Format a Unix timestamp using strftime.
 * Returns a heap-allocated string; caller is responsible for freeing. */
char *rubble_time_format(int64_t ts, const char *fmt) {
    time_t t = (time_t)ts;
    struct tm *tm_info = localtime(&t);
    if (!tm_info) return strdup("");
    char buf[512];
    if (strftime(buf, sizeof(buf), fmt, tm_info) == 0) {
        buf[0] = '\0';
    }
    return strdup(buf);
}
