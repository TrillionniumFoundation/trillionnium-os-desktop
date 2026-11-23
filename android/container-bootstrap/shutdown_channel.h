// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <sys/types.h>

namespace droidloom::bootstrap {

// Bind the inherited manager socket once during Android bootstrap, before fork.
// Both persistent filesystems must already exist in this mount namespace.
bool OpenShutdownChannel();
int ShutdownFd();
bool ReceiveShutdownRequest();
bool AcknowledgeUnmount();

}  // namespace droidloom::bootstrap
