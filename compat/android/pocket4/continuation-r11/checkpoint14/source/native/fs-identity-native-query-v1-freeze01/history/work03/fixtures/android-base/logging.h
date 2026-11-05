#pragma once
#include <cstdlib>
struct FixtureFatal {
    template<class T> FixtureFatal& operator<<(const T&) { return *this; }
    ~FixtureFatal() { std::abort(); }
};
#define LOG(level) FixtureFatal()
#define PLOG(level) FixtureFatal()
