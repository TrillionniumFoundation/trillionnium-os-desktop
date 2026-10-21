#include <openssl/crypto.h>
int main(void) { return OpenSSL_version_num() == 0; }
