
#pragma once
namespace berberis { template<class... T> inline void FixtureTrace(T...) {} }
#define TRACE(...) ::berberis::FixtureTrace(__VA_ARGS__)
