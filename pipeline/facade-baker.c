/* Bake photogrammetric colour onto planar model surfaces (LoD2 walls/roofs).
 * For every texel centre P with outward normal N, a ray starts at P+N*out and travels
 * along -N for out+in metres; the FIRST photo-mesh hit is sampled (bilinear, source UV).
 * Input  (argv[1]): "FBAK1" header, u32 ntex, ntex*(u32 w,h, path[256] of raw RGB),
 *                   u32 ntri, ntri*(f32 xyz*3, f32 uv*3*2, u32 tex),
 *                   u32 nq, f32 out, f32 in, nq*(f32 p[3], n[3])
 * Output (argv[2]): nq*(u8 r,g,b,hit)
 * Build: cc -O3 -o facade-baker facade-baker.c -lpthread
 */
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { float p[9], uv[6]; uint32_t tex; } Tri;
typedef struct { uint32_t w, h; unsigned char *rgb; } Tex;
static Tri *tris; static uint32_t ntri; static Tex *texs; static uint32_t ntex;
static float *q; static uint32_t nq; static float OUT, IN; static unsigned char *res;
static float lo[3], cell = 0.75f; static int dim[3]; static uint32_t *start, *items;

static void rd(void *d, size_t n, FILE *f) { if (fread(d, 1, n, f) != n) { fprintf(stderr, "short read\n"); exit(2); } }
static int ci(float v, int a) { int c = (int)floorf((v - lo[a]) / cell); return c < 0 ? 0 : c >= dim[a] ? dim[a] - 1 : c; }

static void sample(const Tex *t, float u, float v, unsigned char *o) {
    float x = u * t->w - .5f, y = (1.f - v) * t->h - .5f;   /* OBJ v=0 is the bottom row */
    int x0 = (int)floorf(x), y0 = (int)floorf(y); float fx = x - x0, fy = y - y0;
    for (int c = 0; c < 3; c++) {
        float s = 0;
        for (int k = 0; k < 4; k++) {
            int xx = x0 + (k & 1), yy = y0 + (k >> 1);
            xx = xx < 0 ? 0 : xx >= (int)t->w ? t->w - 1 : xx; yy = yy < 0 ? 0 : yy >= (int)t->h ? t->h - 1 : yy;
            s += t->rgb[((size_t)yy * t->w + xx) * 3 + c] * ((k & 1) ? fx : 1 - fx) * ((k >> 1) ? fy : 1 - fy);
        }
        o[c] = (unsigned char)(s + .5f);
    }
}

static int g_threads = 8;
static void *work(void *arg) {
    intptr_t id = (intptr_t)arg;
    for (uint32_t i = (uint32_t)id; i < nq; i += (uint32_t)g_threads) {
        const float *P = q + i * 6, *N = P + 3;
        float o[3] = {P[0] + N[0] * OUT, P[1] + N[1] * OUT, P[2] + N[2] * OUT}, d[3] = {-N[0], -N[1], -N[2]}, L = OUT + IN;
        float e[3] = {o[0] + d[0] * L, o[1] + d[1] * L, o[2] + d[2] * L};
        int a0[3], a1[3];
        for (int a = 0; a < 3; a++) { int c0 = ci(fminf(o[a], e[a]), a), c1 = ci(fmaxf(o[a], e[a]), a); a0[a] = c0; a1[a] = c1; }
        float best = L; int bt = -1; float bu = 0, bv = 0;
        for (int z = a0[2]; z <= a1[2]; z++) for (int y = a0[1]; y <= a1[1]; y++) for (int x = a0[0]; x <= a1[0]; x++) {
            size_t c = ((size_t)z * dim[1] + y) * dim[0] + x;
            for (uint32_t k = start[c]; k < start[c + 1]; k++) {
                const Tri *t = tris + items[k]; const float *A = t->p, *B = t->p + 3, *C = t->p + 6;
                float e1[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]}, e2[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
                float pv[3] = {d[1]*e2[2]-d[2]*e2[1], d[2]*e2[0]-d[0]*e2[2], d[0]*e2[1]-d[1]*e2[0]};
                float det = e1[0]*pv[0] + e1[1]*pv[1] + e1[2]*pv[2]; if (fabsf(det) < 1e-9f) continue;
                float inv = 1.f / det, tv[3] = {o[0]-A[0], o[1]-A[1], o[2]-A[2]};
                float u = (tv[0]*pv[0] + tv[1]*pv[1] + tv[2]*pv[2]) * inv; if (u < 0 || u > 1) continue;
                float qv[3] = {tv[1]*e1[2]-tv[2]*e1[1], tv[2]*e1[0]-tv[0]*e1[2], tv[0]*e1[1]-tv[1]*e1[0]};
                float v = (d[0]*qv[0] + d[1]*qv[1] + d[2]*qv[2]) * inv; if (v < 0 || u + v > 1) continue;
                float tt = (e2[0]*qv[0] + e2[1]*qv[1] + e2[2]*qv[2]) * inv;
                /* only surfaces roughly facing along the query normal: no ground, awning tops or side returns */
                float tn[3] = {e1[1]*e2[2]-e1[2]*e2[1], e1[2]*e2[0]-e1[0]*e2[2], e1[0]*e2[1]-e1[1]*e2[0]};
                float tl = sqrtf(tn[0]*tn[0] + tn[1]*tn[1] + tn[2]*tn[2]);
                if (tl < 1e-12f || fabsf(tn[0]*N[0] + tn[1]*N[1] + tn[2]*N[2]) < .6f * tl) continue;
                if (tt >= 0 && tt < best) { best = tt; bt = (int)items[k]; bu = u; bv = v; }
            }
        }
        unsigned char *r = res + (size_t)i * 4;
        if (bt < 0) { r[0] = r[1] = r[2] = r[3] = 0; continue; }
        const Tri *t = tris + bt; float w0 = 1 - bu - bv;
        sample(texs + t->tex, w0*t->uv[0] + bu*t->uv[2] + bv*t->uv[4], w0*t->uv[1] + bu*t->uv[3] + bv*t->uv[5], r);
        r[3] = 255;
    }
    return NULL;
}
int main(int argc, char **argv) {
    if (argc < 3) return 1;
    FILE *f = fopen(argv[1], "rb"); if (!f) return 1;
    char magic[5]; rd(magic, 5, f); if (memcmp(magic, "FBAK1", 5)) return 1;
    rd(&ntex, 4, f); texs = calloc(ntex, sizeof *texs);
    for (uint32_t i = 0; i < ntex; i++) {
        char path[256]; rd(&texs[i].w, 4, f); rd(&texs[i].h, 4, f); rd(path, 256, f);
        size_t n = (size_t)texs[i].w * texs[i].h * 3; texs[i].rgb = malloc(n);
        FILE *g = fopen(path, "rb"); if (!g || fread(texs[i].rgb, 1, n, g) != n) { fprintf(stderr, "texture %s\n", path); return 2; } fclose(g);
    }
    rd(&ntri, 4, f); tris = malloc((size_t)ntri * sizeof *tris);
    for (uint32_t i = 0; i < ntri; i++) { rd(tris[i].p, 36, f); rd(tris[i].uv, 24, f); rd(&tris[i].tex, 4, f); }
    rd(&nq, 4, f); rd(&OUT, 4, f); rd(&IN, 4, f); q = malloc((size_t)nq * 24); rd(q, (size_t)nq * 24, f); fclose(f);
    float hi[3] = {-1e30f, -1e30f, -1e30f}; lo[0] = lo[1] = lo[2] = 1e30f;
    for (uint32_t i = 0; i < ntri; i++) for (int k = 0; k < 9; k++) { int a = k % 3; lo[a] = fminf(lo[a], tris[i].p[k]); hi[a] = fmaxf(hi[a], tris[i].p[k]); }
    for (int a = 0; a < 3; a++) dim[a] = (int)((hi[a] - lo[a]) / cell) + 1;
    size_t ncell = (size_t)dim[0] * dim[1] * dim[2]; start = calloc(ncell + 1, 4);
    for (int pass = 0; pass < 2; pass++) {
        if (pass) { for (size_t c = 0; c < ncell; c++) start[c + 1] += start[c]; items = malloc((size_t)start[ncell] * 4); }
        uint32_t *fill = pass ? calloc(ncell, 4) : NULL;
        for (uint32_t i = 0; i < ntri; i++) {
            int a0[3], a1[3];
            for (int a = 0; a < 3; a++) { float mn = fminf(fminf(tris[i].p[a], tris[i].p[3 + a]), tris[i].p[6 + a]), mx = fmaxf(fmaxf(tris[i].p[a], tris[i].p[3 + a]), tris[i].p[6 + a]); a0[a] = ci(mn, a); a1[a] = ci(mx, a); }
            for (int z = a0[2]; z <= a1[2]; z++) for (int y = a0[1]; y <= a1[1]; y++) for (int x = a0[0]; x <= a1[0]; x++) {
                size_t c = ((size_t)z * dim[1] + y) * dim[0] + x;
                if (!pass) start[c + 1]++; else items[start[c] + fill[c]++] = i;
            }
        }
        free(fill);
    }
    res = malloc((size_t)nq * 4);
    pthread_t th[64]; for (intptr_t t = 0; t < g_threads; t++) pthread_create(th + t, NULL, work, (void *)t);
    for (int t = 0; t < g_threads; t++) pthread_join(th[t], NULL);
    FILE *o = fopen(argv[2], "wb"); fwrite(res, 4, nq, o); fclose(o);
    uint32_t hits = 0; for (uint32_t i = 0; i < nq; i++) hits += res[i * 4 + 3] != 0;
    fprintf(stderr, "facade-baker: %u triangles, %u queries, %.1f%% hit\n", ntri, nq, 100.0 * hits / (nq ? nq : 1));
    return 0;
}
