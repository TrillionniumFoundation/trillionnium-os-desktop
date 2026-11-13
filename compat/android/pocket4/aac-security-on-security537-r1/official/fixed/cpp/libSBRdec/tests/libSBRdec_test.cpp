/*
 * Copyright (C) 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <gtest/gtest.h>
#include "psdec.h"

// This test verifies the fix for a Use-After-Free (UAF) / Double Free vulnerability
// in CreatePsDec reset branch.
// The vulnerability occurs when CreatePsDec is called to reset an open instance
// (i.e., *h_PS_DEC is not NULL), and subsequently fails.
// Prior to the fix, CreatePsDec would delete the PS decoder handle but not nullify
// the caller's pointer, leading to a dangling pointer.
// This test calls CreatePsDec directly to bypass other SBR decoder checks.
TEST(LibSbrDecTest, CreatePsDecResetUAF) {
  HANDLE_PS_DEC handle = nullptr;

  // 1. First call: Allocate and initialize PS dec successfully with 1024 samples.
  int err = CreatePsDec(&handle, 1024);
  ASSERT_EQ(err, 0);
  ASSERT_NE(handle, nullptr);

  // 2. Second call: Reset with invalid samples (512) to force failure.
  // Since 'handle' is not null, this triggers the reset path.
  err = CreatePsDec(&handle, 512);
  EXPECT_NE(err, 0);

  // If the patch is NOT applied:
  // - CreatePsDec already called DeletePsDec internally, freeing the memory.
  // - But 'handle' was not nullified, so it is dangling.
  // - The following DeletePsDec call will attempt to free it again (double free -> crash).
  //
  // If the patch IS applied:
  // - CreatePsDec did NOT free the memory because it was not locally allocated.
  // - 'handle' is still valid.
  // - The following DeletePsDec call will safely free it and set 'handle' to nullptr.
  if (handle != nullptr) {
    DeletePsDec(&handle);
  }

  EXPECT_EQ(handle, nullptr);
}
