/*
 * Rubble json module — rubble_json.c
 *
 * A minimal, self-contained JSON parser/emitter. No dependencies.
 *
 * Rubble API:
 *   json.encode(text)        -> text    wrap a raw value in a JSON string
 *   json.decode(text)        -> text    parse JSON, return root as opaque handle (text ptr)
 *   json.get(handle, key)    -> text    get a string value by dot-path key (e.g. "user.name")
 *   json.set(handle, key, v) -> text    set a value, return modified JSON text
 *
 * Design:
 *   "handle" in Rubble is just the raw JSON text — decode validates it and returns
 *   the same pointer (or a normalised copy). get/set do text-level key lookup.
 *   This is intentionally simple — covers config files and REST API responses.
 */

#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>

/* ── Helpers ──────────────────────────────────────────────────────────── */

static const char *_skip_ws(const char *p) {
    while (p && isspace((unsigned char)*p)) p++;
    return p;
}

/* Skip over a JSON value starting at p; return pointer just past it */
static const char *_skip_value(const char *p);

static const char *_skip_string(const char *p) {
    if (!p || *p != '"') return p;
    p++;
    while (*p) {
        if (*p == '\\') { p++; if (*p) p++; continue; }
        if (*p == '"')  { p++; return p; }
        p++;
    }
    return p;
}

static const char *_skip_value(const char *p) {
    p = _skip_ws(p);
    if (!p || !*p) return p;
    if (*p == '"') return _skip_string(p);
    if (*p == '{') {
        p++;
        while (*p) {
            p = _skip_ws(p);
            if (*p == '}') return p + 1;
            p = _skip_string(_skip_ws(p));   /* key */
            p = _skip_ws(p);
            if (*p == ':') p++;
            p = _skip_value(p);              /* value */
            p = _skip_ws(p);
            if (*p == ',') p++;
        }
        return p;
    }
    if (*p == '[') {
        p++;
        while (*p) {
            p = _skip_ws(p);
            if (*p == ']') return p + 1;
            p = _skip_value(p);
            p = _skip_ws(p);
            if (*p == ',') p++;
        }
        return p;
    }
    /* number, bool, null */
    while (*p && *p != ',' && *p != '}' && *p != ']' && !isspace((unsigned char)*p))
        p++;
    return p;
}

/* Extract string value of a key from a JSON object (top-level only).
 * Returns heap-allocated unquoted string or NULL. */
static char *_get_key(const char *json, const char *key) {
    const char *p = _skip_ws(json);
    if (!p || *p != '{') return NULL;
    p++;
    while (*p) {
        p = _skip_ws(p);
        if (*p == '}') break;
        /* Read key */
        if (*p != '"') break;
        const char *ks = p + 1;
        p = _skip_string(p);
        size_t klen = (size_t)(p - ks - 1);  /* -1 for closing " */
        p = _skip_ws(p);
        if (*p == ':') p++;
        p = _skip_ws(p);
        /* Compare key */
        if (strlen(key) == klen && strncmp(key, ks, klen) == 0) {
            /* Extract value */
            if (*p == '"') {
                /* String value — return unquoted */
                const char *vs = p + 1;
                p = _skip_string(p);
                size_t vlen = (size_t)(p - vs - 1);
                char *result = (char *)malloc(vlen + 1);
                if (!result) return NULL;
                memcpy(result, vs, vlen);
                result[vlen] = '\0';
                return result;
            } else {
                /* Non-string value — return as-is */
                const char *vs = p;
                p = _skip_value(p);
                size_t vlen = (size_t)(p - vs);
                char *result = (char *)malloc(vlen + 1);
                if (!result) return NULL;
                memcpy(result, vs, vlen);
                result[vlen] = '\0';
                return result;
            }
        }
        /* Skip value */
        p = _skip_value(p);
        p = _skip_ws(p);
        if (*p == ',') p++;
    }
    return NULL;
}

/* ── Public API ───────────────────────────────────────────────────────── */

/* encode: escape a plain string into a JSON string literal */
char *rubble_json_encode(const char *s) {
    size_t len = strlen(s);
    /* Worst case: every char becomes \uXXXX (6 chars) + 2 quotes + null */
    char *buf = (char *)malloc(len * 6 + 3);
    if (!buf) return strdup("\"\"");
    char *dst = buf;
    *dst++ = '"';
    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)s[i];
        if      (c == '"')  { *dst++ = '\\'; *dst++ = '"'; }
        else if (c == '\\') { *dst++ = '\\'; *dst++ = '\\'; }
        else if (c == '\n') { *dst++ = '\\'; *dst++ = 'n'; }
        else if (c == '\r') { *dst++ = '\\'; *dst++ = 'r'; }
        else if (c == '\t') { *dst++ = '\\'; *dst++ = 't'; }
        else if (c < 0x20)  { dst += sprintf(dst, "\\u%04x", c); }
        else                 { *dst++ = (char)c; }
    }
    *dst++ = '"';
    *dst   = '\0';
    return buf;
}

/* decode: validate and return the JSON text (no-op for now — just strdup) */
char *rubble_json_decode(const char *json) {
    return strdup(json ? json : "null");
}

/* get: retrieve a value by dot-path key ("user.name", "items.0") */
char *rubble_json_get(const char *json, const char *key) {
    /* Handle dot-path by recursing one segment at a time */
    char *dot = strchr(key, '.');
    if (!dot) {
        char *v = _get_key(json, key);
        return v ? v : strdup("");
    }
    /* Split key at first dot */
    size_t seg_len = (size_t)(dot - key);
    char *seg = (char *)malloc(seg_len + 1);
    if (!seg) return strdup("");
    memcpy(seg, key, seg_len);
    seg[seg_len] = '\0';
    char *sub_json = _get_key(json, seg);
    free(seg);
    if (!sub_json) return strdup("");
    char *result = rubble_json_get(sub_json, dot + 1);
    free(sub_json);
    return result;
}

/* set: set a top-level string key and return new JSON text.
 * This is a simple text-level replacement — doesn't handle nested paths.
 * If key exists, replaces the value; otherwise appends it. */
char *rubble_json_set(const char *json, const char *key, const char *value) {
    const char *p = _skip_ws(json);
    if (!p || *p != '{') {
        /* Build a new object */
        char *encoded_val = rubble_json_encode(value);
        size_t encoded_key_len = strlen(key) + 2 + 2 + strlen(encoded_val) + 4;
        char *result = (char *)malloc(encoded_key_len + 8);
        if (!result) { free(encoded_val); return strdup("{}"); }
        sprintf(result, "{\"%s\": %s}", key, encoded_val);
        free(encoded_val);
        return result;
    }

    /* Find existing key and replace, or insert before closing } */
    char *encoded_val = rubble_json_encode(value);
    size_t jlen = strlen(json);
    /* Build new JSON by copying and patching */
    char *out = (char *)malloc(jlen + strlen(key) + strlen(encoded_val) + 32);
    if (!out) { free(encoded_val); return strdup(json); }

    /* Locate the key inside the object */
    size_t klen = strlen(key);
    char search[512];
    snprintf(search, sizeof(search), "\"%s\"", key);
    const char *found = strstr(json, search);
    const char *colon = found ? strstr(found + strlen(search), ":") : NULL;

    if (found && colon) {
        /* Copy up to the colon, then write new value, then skip old value */
        size_t prefix_len = (size_t)(colon - json) + 1;
        memcpy(out, json, prefix_len);
        out[prefix_len] = ' ';
        strcpy(out + prefix_len + 1, encoded_val);
        const char *rest = _skip_value(_skip_ws(colon + 1));
        strcat(out, rest);
    } else {
        /* Key not found — insert before the closing } */
        size_t close_pos = jlen - 1;
        while (close_pos > 0 && json[close_pos] != '}') close_pos--;
        memcpy(out, json, close_pos);
        out[close_pos] = '\0';
        /* Add comma if object is non-empty */
        const char *inner_start = _skip_ws(json + 1);
        if (inner_start && *inner_start != '}') strcat(out, ", ");
        sprintf(out + strlen(out), "\"%s\": %s}", key, encoded_val);
    }

    free(encoded_val);
    return out;
}
