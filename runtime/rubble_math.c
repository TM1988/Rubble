/*
 * Rubble Math Library — rubble_math.c
 * Wraps standard C math functions for use from Rubble's `math` stdlib.
 *
 * Rubble API (all use decimal / double):
 *   math.sqrt(x)        math.cbrt(x)
 *   math.pow(base, exp) math.abs(x)
 *   math.floor(x)       math.ceil(x)    math.round(x)
 *   math.sin(x)         math.cos(x)     math.tan(x)
 *   math.asin(x)        math.acos(x)    math.atan(x)
 *   math.atan2(y, x)
 *   math.log(x)         math.log2(x)    math.log10(x)
 *   math.exp(x)
 *   math.min(a, b)      math.max(a, b)
 *   math.pi()  -> decimal (3.14159...)
 *   math.e()   -> decimal (2.71828...)
 *   math.inf() -> decimal (infinity)
 *   math.clamp(val, lo, hi) -> decimal
 *   math.lerp(a, b, t)      -> decimal
 */

#define _CRT_SECURE_NO_WARNINGS
#include <math.h>
#include <stdint.h>

#ifndef M_PI
  #define M_PI 3.14159265358979323846
#endif
#ifndef M_E
  #define M_E  2.71828182845904523536
#endif

double rubble_math_sqrt(double x)           { return sqrt(x); }
double rubble_math_cbrt(double x)           { return cbrt(x); }
double rubble_math_pow(double b, double e)  { return pow(b, e); }
double rubble_math_abs(double x)            { return fabs(x); }
double rubble_math_floor(double x)          { return floor(x); }
double rubble_math_ceil(double x)           { return ceil(x); }
double rubble_math_round(double x)          { return round(x); }
double rubble_math_sin(double x)            { return sin(x); }
double rubble_math_cos(double x)            { return cos(x); }
double rubble_math_tan(double x)            { return tan(x); }
double rubble_math_asin(double x)           { return asin(x); }
double rubble_math_acos(double x)           { return acos(x); }
double rubble_math_atan(double x)           { return atan(x); }
double rubble_math_atan2(double y, double x){ return atan2(y, x); }
double rubble_math_log(double x)            { return log(x); }
double rubble_math_log2(double x)           { return log2(x); }
double rubble_math_log10(double x)          { return log10(x); }
double rubble_math_exp(double x)            { return exp(x); }
double rubble_math_min(double a, double b)  { return a < b ? a : b; }
double rubble_math_max(double a, double b)  { return a > b ? a : b; }
double rubble_math_pi(void)                 { return M_PI; }
double rubble_math_e(void)                  { return M_E; }
double rubble_math_inf(void)                { return (double)(1.0/0.0); }
double rubble_math_clamp(double v, double lo, double hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}
double rubble_math_lerp(double a, double b, double t) {
    return a + t * (b - a);
}
