
#pragma once
#include <cstdlib>
#define CHECK(x) do { if (!(x)) std::abort(); } while (0)
#define CHECK_NE(x,y) CHECK((x)!=(y))
