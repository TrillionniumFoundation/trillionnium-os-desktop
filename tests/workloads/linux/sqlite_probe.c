#define _GNU_SOURCE
#include <sqlite3.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static int sql(sqlite3 *db, const char *text) {
    char *err = NULL;
    int rc = sqlite3_exec(db, text, NULL, NULL, &err);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "sqlite %d: %s (SQL: %.90s)\n", rc, err ? err : sqlite3_errmsg(db), text);
        sqlite3_free(err);
        return 1;
    }
    return 0;
}
static int open_db(sqlite3 **db, const char *path) {
    int rc = sqlite3_open_v2(path, db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, NULL);
    if (rc != SQLITE_OK) { fprintf(stderr, "open error %d\n", rc); return 1; }
    sqlite3_busy_timeout(*db, 10000);
    return 0;
}
static int scalar(sqlite3 *db, const char *query, char *result, int cap) {
    sqlite3_stmt *st = NULL;
    if (sqlite3_prepare_v2(db, query, -1, &st, NULL) != SQLITE_OK) return 1;
    int rc = sqlite3_step(st);
    if (rc != SQLITE_ROW) { sqlite3_finalize(st); return 1; }
    const unsigned char *p = sqlite3_column_text(st, 0);
    if (!p || (int)strlen((const char*)p) >= cap) { sqlite3_finalize(st); return 1; }
    snprintf(result, (size_t)cap, "%s", p);
    return sqlite3_finalize(st) != SQLITE_OK;
}
static int writer(const char *path, char prefix) {
    sqlite3 *db = NULL;
    if (open_db(&db, path)) return 2;
    for (int i = 0; i < 20; i++) {
        char cmd[128];
        snprintf(cmd, sizeof cmd, "INSERT INTO events VALUES('%c%02d',%d)", prefix, i, i);
        if (sql(db, "BEGIN IMMEDIATE") || sql(db, cmd) || sql(db, "COMMIT")) return 3;
    }
    return sqlite3_close(db) == SQLITE_OK ? 0 : 4;
}
static int wait_exit(pid_t pid, int expected) {
    int status = 0;
    return waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == expected;
}
int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: %s WORK_DIR\n", argv[0]); return 64; }
    char path[4096];
    if (snprintf(path, sizeof path, "%s/wal-sqlite-c.db", argv[1]) >= (int)sizeof path) return 60;
    sqlite3 *db = NULL;
    if (open_db(&db, path)) return 1;
    char mode[32];
    if (scalar(db, "PRAGMA journal_mode=WAL", mode, sizeof mode) || strcmp(mode,"wal")) return 2;
    if (sql(db, "CREATE TABLE events(id TEXT PRIMARY KEY, n INTEGER NOT NULL)")) return 3;
    if (sqlite3_close(db) != SQLITE_OK) return 4;
    pid_t a = fork();
    if (a < 0) return 5;
    if (a == 0) _exit(writer(path, 'A'));
    pid_t b = fork();
    if (b < 0) return 6;
    if (b == 0) _exit(writer(path, 'B'));
    if (!wait_exit(a, 0) || !wait_exit(b, 0)) return 7;
    pid_t crash = fork();
    if (crash < 0) return 8;
    if (crash == 0) {
        if (open_db(&db, path) || sql(db, "INSERT INTO events VALUES('committed',41)")) _exit(8);
        if (sql(db, "BEGIN IMMEDIATE") || sql(db, "INSERT INTO events VALUES('uncommitted',42)")) _exit(9);
        _exit(37); /* no COMMIT; real worker process exits abruptly */
    }
    if (!wait_exit(crash, 37)) return 9;
    if (open_db(&db, path)) return 10;
    char count[32], old[32], confirmed[32], integrity[64];
    if (scalar(db, "SELECT count(*) FROM events", count, sizeof count) || strcmp(count,"41")) return 11;
    if (scalar(db, "SELECT count(*) FROM events WHERE id='uncommitted'", old, sizeof old) || strcmp(old,"0")) return 12;
    if (scalar(db, "SELECT count(*) FROM events WHERE id='committed'", confirmed, sizeof confirmed) || strcmp(confirmed,"1")) return 13;
    if (scalar(db, "PRAGMA integrity_check", integrity, sizeof integrity) || strcmp(integrity,"ok")) return 14;
    int busy = -1;
    if (sqlite3_wal_checkpoint_v2(db, NULL, SQLITE_CHECKPOINT_TRUNCATE, NULL, NULL) != SQLITE_OK) return 15;
    busy = 0;
    if (sqlite3_close(db) != SQLITE_OK) return 16;
    if (open_db(&db, path)) return 17;
    if (scalar(db, "SELECT count(*) FROM events", count, sizeof count) || strcmp(count,"41")) return 18;
    if (sqlite3_close(db) != SQLITE_OK) return 19;
    printf("{\"ok\":true,\"journal_mode\":\"wal\",\"rows_after_reopen\":41,\"concurrent_commits\":40,\"committed_visible\":true,\"uncommitted_visible\":false,\"crash_exit_code\":37,\"integrity_check\":\"ok\",\"checkpoint_busy\":%d}\n", busy);
    return 0;
}
