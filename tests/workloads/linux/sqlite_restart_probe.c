#define _GNU_SOURCE
#include <sqlite3.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Guest-kernel crash/reopen evidence. Host power loss and device volatile-cache
 * loss are separate tests: killing QEMU does not discard the host page cache. */
static int execute(sqlite3 *db, const char *sql) {
    char *message = NULL;
    int rc = sqlite3_exec(db, sql, NULL, NULL, &message);
    if (rc != SQLITE_OK)
        fprintf(stderr, "SQLITE_RESTART_ERROR rc=%d detail=%s\n", rc,
                message ? message : sqlite3_errmsg(db));
    sqlite3_free(message);
    return rc == SQLITE_OK ? 0 : 1;
}

static int scalar(sqlite3 *db, const char *sql, const char *expected) {
    sqlite3_stmt *statement = NULL;
    if (sqlite3_prepare_v2(db, sql, -1, &statement, NULL) != SQLITE_OK) return 1;
    int rc = sqlite3_step(statement);
    const unsigned char *actual = rc == SQLITE_ROW ? sqlite3_column_text(statement, 0) : NULL;
    int equal = actual && strcmp((const char *)actual, expected) == 0;
    int complete = equal && sqlite3_step(statement) == SQLITE_DONE;
    return sqlite3_finalize(statement) != SQLITE_OK || !complete;
}

static int seed(sqlite3 *db, const char *directory, const char *nonce, int omit_commit) {
    if (scalar(db, "PRAGMA journal_mode=WAL", "wal") ||
        execute(db, "PRAGMA synchronous=FULL; PRAGMA wal_autocheckpoint=0; PRAGMA cache_size=8") ||
        scalar(db, "PRAGMA synchronous", "2") ||
        execute(db, "CREATE TABLE evidence(id INTEGER PRIMARY KEY, body BLOB NOT NULL)")) return 10;
    sqlite3_stmt *statement = NULL;
    if (sqlite3_prepare_v2(db, "INSERT INTO evidence VALUES(0,?1)", -1, &statement, NULL) != SQLITE_OK)
        return 11;
    if (sqlite3_bind_text(statement, 1, nonce, -1, SQLITE_STATIC) != SQLITE_OK ||
        sqlite3_step(statement) != SQLITE_DONE) { sqlite3_finalize(statement); return 12; }
    if (sqlite3_finalize(statement) != SQLITE_OK || execute(db, "BEGIN IMMEDIATE")) return 13;
    for (int i = 1; i <= 32; i++) {
        char sql[96];
        snprintf(sql, sizeof sql, "INSERT INTO evidence VALUES(%d,zeroblob(4096))", i);
        if (execute(db, sql)) return 14;
    }
    if (!omit_commit && (execute(db, "COMMIT") || execute(db, "BEGIN IMMEDIATE"))) return 15;
    for (int i = 1001; i <= 1016; i++) {
        char sql[96];
        snprintf(sql, sizeof sql, "INSERT INTO evidence VALUES(%d,zeroblob(4096))", i);
        if (execute(db, sql)) return 16;
    }
    /* Force dirty pages out of SQLite's small cache without committing the
     * pending transaction. Recovery must distinguish WAL commit boundaries. */
    if (sqlite3_db_cacheflush(db) != SQLITE_OK) return 17;
    int parent = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (parent < 0) return 18;
    int synced = fsync(parent);
    int closed = close(parent);
    if (synced || closed) return 19;
    printf("SQLITE_RESTART_READY nonce=%s committed=%d pending=16 synchronous=FULL\n",
           nonce, omit_commit ? 0 : 32);
    fflush(stdout);
    for (;;) pause();  /* Host kills the task-owned emulator, never clean close. */
}

static int verify(sqlite3 *db, const char *nonce) {
    if (scalar(db, "PRAGMA integrity_check", "ok") ||
        scalar(db, "PRAGMA journal_mode", "wal") ||
        scalar(db, "SELECT body FROM evidence WHERE id=0", nonce) ||
        scalar(db, "SELECT count(*) FROM evidence WHERE id BETWEEN 1 AND 32 AND length(body)=4096", "32") ||
        scalar(db, "SELECT count(*) FROM evidence WHERE id>=1000", "0") ||
        scalar(db, "SELECT count(*) FROM evidence", "33")) {
        fprintf(stderr, "SQLITE_RESTART_REJECTED nonce=%s\n", nonce);
        return 20;
    }
    printf("SQLITE_RESTART_VERIFIED nonce=%s committed=32 pending=0 integrity=ok\n", nonce);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 4 || strlen(argv[3]) != 64 || strspn(argv[3], "0123456789abcdef") != 64)
        return 64;
    int reading = strcmp(argv[1], "verify") == 0;
    int omit_commit = strcmp(argv[1], "seed-uncommitted") == 0;
    if (!reading && !omit_commit && strcmp(argv[1], "seed") != 0) return 64;
    char path[4096];
    if (snprintf(path, sizeof path, "%s/restart.db", argv[2]) >= (int)sizeof path) return 65;
    struct stat info;
    int exists = lstat(path, &info) == 0;
    if ((reading && (!exists || !S_ISREG(info.st_mode))) || (!reading && (exists || errno != ENOENT)))
        return 66;
    sqlite3 *db = NULL;
    int flags = SQLITE_OPEN_READWRITE | (reading ? 0 : SQLITE_OPEN_CREATE);
    if (sqlite3_open_v2(path, &db, flags, NULL) != SQLITE_OK) return 67;
    sqlite3_busy_timeout(db, 3000);
    int result = reading ? verify(db, argv[3]) : seed(db, argv[2], argv[3], omit_commit);
    if (sqlite3_close(db) != SQLITE_OK && !result) result = 68;
    return result;
}
