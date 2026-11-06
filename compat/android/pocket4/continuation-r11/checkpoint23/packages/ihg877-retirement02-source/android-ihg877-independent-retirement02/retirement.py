import json
INPUTS=json.loads("{\n  \"schema\": \"pocket4-independent-current-IHG877-retirement-input-v1\",\n  \"task\": 877,\n  \"package\": \"com.ihg.apps.android\",\n  \"component\": \"com.ihg.apps.android/com.ihg.apps.android.activity.MainActivity\",\n  \"original_launch_outcome\": \"unknown_retained\",\n  \"native_reported_task_id\": null,\n  \"old_task876_disappearance_attributed\": false,\n  \"fixed_historical_files\": {\n    \"attempted\": {\n      \"bytes\": 1052,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/launch-attempted.json\",\n      \"sha256\": \"7bc83190a0fe9339dda79bcd8508b9e8d5c12786178e680c00ea5795e83070ec\"\n    },\n    \"coordinator\": {\n      \"bytes\": 6175,\n      \"path\": \"/home/alex/work/pocket4-ihg-r4-public-london-input-01/result.json\",\n      \"sha256\": \"09e528df22c01ffbb293264309c028ce549666602e4a97669c3eac80d62488b1\"\n    },\n    \"native_intent\": {\n      \"bytes\": 909,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/command-007.intent.json\",\n      \"sha256\": \"2d0f835e97fe55d7fa9ebdeb67d7ee14338d9f6ece2f4395f26a10448f867b18\"\n    },\n    \"native_result\": {\n      \"bytes\": 442,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/command-007.result.json\",\n      \"sha256\": \"5e913c8dc9e0935a56eaa4cfa5cddef1103a3b4d692f482d9e00bd36e90a1a2a\"\n    },\n    \"native_stderr\": {\n      \"bytes\": 554,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/command-007.stderr\",\n      \"sha256\": \"8c88d864bc639295535a7e1ad3b80524162066f5179109f0bc6dfd4d25c5b6b4\"\n    },\n    \"native_stdout\": {\n      \"bytes\": 625,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/command-007.stdout\",\n      \"sha256\": \"527b57dfcdb2d4a5ac88b9e3fdff8c3dda343f1d73436573131ca6886068ef8e\"\n    },\n    \"prelaunch_result\": {\n      \"bytes\": 444,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/command-006.result.json\",\n      \"sha256\": \"64f9d16e62eec92696f04c71d4415403d3dc3279015304922fd1beb3c15add65\"\n    },\n    \"prelaunch_stacks\": {\n      \"bytes\": 1310,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/prelaunch-stacks.txt\",\n      \"sha256\": \"c3b00790148c3dba93483942721ba45c7b046fe65d50b7a74a3085fc97ca2453\"\n    },\n    \"prelaunch_stdout\": {\n      \"bytes\": 1310,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/command-006.stdout\",\n      \"sha256\": \"c3b00790148c3dba93483942721ba45c7b046fe65d50b7a74a3085fc97ca2453\"\n    },\n    \"prelaunch_transport\": {\n      \"bytes\": 661,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/transport-006.verified-result.json\",\n      \"sha256\": \"d131dac48127405cbb831a88a9a90eb5c1104bab8f3260d73f9059898141b588\"\n    },\n    \"recorder_source\": {\n      \"bytes\": 41689,\n      \"path\": \"/home/alex/work/pocket4-current-host-r6-source-01/recorder.py\",\n      \"sha256\": \"c63cbdca615a609ebb41bcb25db6b770f43c4488c46a8f7b1dbee4bc462b4e64\"\n    },\n    \"scope\": {\n      \"bytes\": 934,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/scope.json\",\n      \"sha256\": \"62fbe9c2c993b2104dd762eee66a3e8cb3f6bcbfad5bc61826186cbcd8e44dce\"\n    },\n    \"stage\": {\n      \"bytes\": 2187,\n      \"path\": \"/home/alex/work/pocket4-ihg-r4-public-london-input-01/stage-result.json\",\n      \"sha256\": \"a4b5d60e30dd33ad06a4e127b6bb41c22bf7639a0c7842dd5ea6b74de5465d59\"\n    },\n    \"task_parser\": {\n      \"bytes\": 17281,\n      \"path\": \"/home/alex/work/pocket4-current-host-r6-source-01/references/task_scope_baseline.py\",\n      \"sha256\": \"a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528\"\n    },\n    \"worker\": {\n      \"bytes\": 12051,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/launch-01/result.json\",\n      \"sha256\": \"3ab8190051ab6c628a7e6b67c0f10567cb18e273db6ecc067b5856098e37034b\"\n    }\n  },\n  \"native_projection\": {\n    \"closed_child_matches\": [],\n    \"closed_word_flags\": {\n      \"crash\": false,\n      \"denied\": false,\n      \"failed\": true,\n      \"launch\": true,\n      \"launcher\": true,\n      \"ownership\": false,\n      \"permission\": false,\n      \"registered\": false,\n      \"signal\": false,\n      \"task\": true,\n      \"timeout\": true\n    },\n    \"complete_wrapper_match\": false,\n    \"current_installed_source_version_verified\": false,\n    \"expected_launcher_host_pid_match\": true,\n    \"format\": \"known_four_field_JSON\",\n    \"host_pid\": 3268774,\n    \"line_count\": 7,\n    \"line_metadata\": [\n      {\n        \"bytes\": 246,\n        \"sha256\": \"7c0ef44698985c606b23cbfcce0b17a87072fbab9421f12dbc1724437a728c79\"\n      },\n      {\n        \"bytes\": 171,\n        \"sha256\": \"81853965c08867c00d476c3450370827ac9ff3322ee071e7fb80981926bfe0b7\"\n      },\n      {\n        \"bytes\": 15,\n        \"sha256\": \"c54c75bbef244ae0a9f15dfeb3c69e29a6b8ebb0df38d52213129b7c87c63d55\"\n      },\n      {\n        \"bytes\": 25,\n        \"sha256\": \"ec0780d9b68fd98dcc5389cbc641e254ac631c85cc5a648161af80a5ab2359c2\"\n      },\n      {\n        \"bytes\": 53,\n        \"sha256\": \"095ba5c36f94fc55019f4813d0f4104840b80a07388079a82291ea155fb1fd71\"\n      },\n      {\n        \"bytes\": 15,\n        \"sha256\": \"6e85672f0b96fa505ec36d1fefbc982ee358501e7fcece3c41ceb83f398c43a8\"\n      },\n      {\n        \"bytes\": 8,\n        \"sha256\": \"143b270a32602d412babf2724ec0640dda0d5a43485e5a7520b05b53fa94b303\"\n      }\n    ],\n    \"message\": {\n      \"bytes\": 539,\n      \"sha256\": \"a2d6e620363ff8486d64a331f5dabe250713cabb582af4cbe537a5bed84bb8ac\"\n    },\n    \"ok\": false,\n    \"raw_streams_exported\": false,\n    \"state\": \"running\",\n    \"state_sha256\": \"c071cf5f5ed6f884cc70155b6f05f755fd46a302d05e4261b7e92ce878bbfed8\",\n    \"stderr\": {\n      \"bytes\": 554,\n      \"sha256\": \"8c88d864bc639295535a7e1ad3b80524162066f5179109f0bc6dfd4d25c5b6b4\"\n    },\n    \"stderr_exactly_repeats_complete_message\": true,\n    \"stdout\": {\n      \"bytes\": 625,\n      \"sha256\": \"527b57dfcdb2d4a5ac88b9e3fdff8c3dda343f1d73436573131ca6886068ef8e\"\n    },\n    \"task_cleanup_authority_created\": false,\n    \"whole_error_attribution_qualified\": false\n  },\n  \"prelaunch\": {\n    \"complete_parsed_roots_sha256\": \"088ebb3a78acb4757a7b91eeb9ca5c509841dd570471df2acaf657daaf967789\",\n    \"raw_pin\": {\n      \"bytes\": 1310,\n      \"sha256\": \"c3b00790148c3dba93483942721ba45c7b046fe65d50b7a74a3085fc97ca2453\"\n    },\n    \"roots\": [\n      {\n        \"children\": [\n          {\n            \"component_sha256\": \"ab0de58e3840aa30ba5440cd982e543b9c02517d8d8204bfcd3c51166bf7f513\",\n            \"component_utf8_bytes\": 66,\n            \"id\": 875,\n            \"public_target_component\": null,\n            \"target_component_match\": false,\n            \"user\": 0\n          }\n        ],\n        \"complete_root_record_sha256\": \"d7cf29998b32a57a3680dd9e3b5b1af813a2cde6216db4f376403e633cc3618a\",\n        \"display\": 0,\n        \"freeform\": false,\n        \"id\": 1,\n        \"user\": 0\n      },\n      {\n        \"children\": [\n          {\n            \"component_sha256\": \"c4af06acbbcc90d8d1c4d7e5e07fc9d09c20998956e86760c1b1b9231f6bb28a\",\n            \"component_utf8_bytes\": 51,\n            \"id\": 876,\n            \"public_target_component\": null,\n            \"target_component_match\": false,\n            \"user\": 0\n          }\n        ],\n        \"complete_root_record_sha256\": \"f33510bbd5852dde371081b31411f58980707f913ce376944b790272934ea50a\",\n        \"display\": 0,\n        \"freeform\": true,\n        \"id\": 876,\n        \"user\": 0\n      }\n    ],\n    \"task_cleanup_authority_created\": false,\n    \"tasks\": [\n      875,\n      876\n    ],\n    \"unknown_component_names_exported\": false\n  },\n  \"current_saved\": [\n    {\n      \"sample\": 1,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/native-launch-state-read-02/current-stacks-01.txt\",\n      \"bytes\": 1326,\n      \"sha256\": \"b7e0d5df2bc42d78691443a55ee4d30303e4513ac48fa525f26ae985085b7973\",\n      \"command\": {\n        \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/native-launch-state-read-02/command-005.result.json\",\n        \"bytes\": 443,\n        \"sha256\": \"fa50e117d7064a10750657174e13cd400bf2cb4464e8cdbc5711e4678bce9ae7\"\n      },\n      \"parsed_roots_sha256\": \"623589a06d53ff445a30a59a1b89dc4793eba18d1b5654fc0606700d92c427da\"\n    },\n    {\n      \"sample\": 2,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/native-launch-state-read-02/current-stacks-02.txt\",\n      \"bytes\": 1326,\n      \"sha256\": \"b7e0d5df2bc42d78691443a55ee4d30303e4513ac48fa525f26ae985085b7973\",\n      \"command\": {\n        \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/native-launch-state-read-02/command-006.result.json\",\n        \"bytes\": 444,\n        \"sha256\": \"19e48f6ca380a854f992e6dd47ec1708fce0fc4870968e684f09a39245dd75a7\"\n      },\n      \"parsed_roots_sha256\": \"623589a06d53ff445a30a59a1b89dc4793eba18d1b5654fc0606700d92c427da\"\n    }\n  ],\n  \"current_tasks\": [\n    875,\n    877\n  ],\n  \"preserved_current_tasks\": [\n    875\n  ],\n  \"preserved_current_root_ids\": [\n    1\n  ],\n  \"preserved_root1_sha256\": \"d7cf29998b32a57a3680dd9e3b5b1af813a2cde6216db4f376403e633cc3618a\",\n  \"current_root877_sha256\": \"8539928b108b7b26fec241c4d3cb1ff010aa600269f78bf6c0c0e16f11f7f588\",\n  \"evidence\": {\n    \"native007\": {\n      \"tree\": \"f263f4246200cb8d3f528050b29de7ca3bf8929f\",\n      \"blob\": \"a1ddcaa607b2b48df1f7342b3890c55e58cdd54a\",\n      \"bytes\": 9085,\n      \"sha256\": \"243e6c6fe1b16c0cd6c22488fdf1a58cee2949796b094062792f5917ff21594b\"\n    },\n    \"current_read02\": {\n      \"tree\": \"42f9f8c4fb7f09261e078a88a7e0ed92c25dce5e\",\n      \"blob\": \"da1850b3bddf3a3458c9f186be6d4220c93e845d\",\n      \"bytes\": 20862,\n      \"sha256\": \"96d58a756c7e5179ced035925d99508955163a72a4f452f030a25f18df79e157\"\n    },\n    \"saved_projection\": {\n      \"tree\": \"5a884717ccbae97944a0dd84dd446f05f44b9c47\",\n      \"blob\": \"987766857453e90b47eb57150d9bdb45c30cc96a\",\n      \"bytes\": 4293,\n      \"sha256\": \"e7d04dfd8746d1a847e1e0420b5985f36aafc04b3223747558ca949e3702f062\"\n    }\n  },\n  \"current_retirement02_baseline\": {\n    \"schema\": \"pocket4-independent-current-IHG877-retirement02-baseline-v1\",\n    \"actual_failed_retirement\": {\n      \"tree\": \"9398613a97fc015d4d202c50f1ffffcfa4213de6\",\n      \"blob\": \"eef5723a89f6e55c3cb6dec46d593e4b18d38178\",\n      \"bytes\": 24051,\n      \"sha256\": \"dd040d4a5ac8050a2fd3d854e0dec74be386c048f33b68d0e4b200aaa4a79e9a\"\n    },\n    \"actual_saved_projection\": {\n      \"tree\": \"7e292c099ab91f6ee0baf677edaeeedae20f761f\",\n      \"blob\": \"690f9bf079567e23b9ac44194d5918fc92a5844c\",\n      \"bytes\": 6956,\n      \"sha256\": \"c0a2ba798ead0f887b44f86a0e124e38762039d4b2bd9d309ad0ec648056ff70\"\n    },\n    \"prior_failed_run\": {\n      \"source_sha256\": \"c2f3d2e849d3d2dbabd58d5c6ebf35ad7cb6c729a153a94bf415f780fb94fbfc\",\n      \"step_name\": \"current-ihg877-independent-retirement-01\",\n      \"first_error\": {\n        \"exception_type\": \"RuntimeError\",\n        \"fixed_code\": \"OTHER_TASK_SET_CHANGED\",\n        \"message_sha256\": \"822aca1d3693d9ce997c9600640cb0abbb958113cf18c14feb0c2bd957073bc3\",\n        \"phase\": \"current_complete_table_1\",\n        \"raw_message_exported\": false\n      },\n      \"ok\": false,\n      \"remove_requested\": false,\n      \"remove_acknowledged\": false,\n      \"removal_action_attempted\": false,\n      \"retirement_outcome_unknown\": false,\n      \"actual_command_count\": 9,\n      \"controls_passed\": 38,\n      \"helper_UiAutomation_calls\": 0,\n      \"native_launches\": 0,\n      \"historical_launch_outcome\": \"unknown_retained\",\n      \"current_Main_window_complete\": true,\n      \"Main_before_lock\": {\n        \"Main_epoch_sha256\": \"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\n        \"authenticated_owner_chain_matches\": true,\n        \"config_sha256\": \"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\n        \"current_baseline_qualification_sha256\": \"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\n        \"current_baseline_sha256\": \"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\n        \"current_executable_and_root_backing_match\": true,\n        \"current_user_namespaces_match\": true,\n        \"framework_exit_cause_resolved\": false,\n        \"historical_activation_sha256\": \"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\n        \"historical_verified_sha256\": \"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\n        \"old_helpers_and_tasks_reauthorized\": false,\n        \"previous_current_baseline_sha256\": \"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\n        \"production_ready\": false,\n        \"resource_limits_match\": true,\n        \"schema\": \"pocket4-current-main-guard-v2\",\n        \"seven_processes_match\": true,\n        \"three_host_processes_match\": true\n      },\n      \"Main_after_locks\": {\n        \"Main_epoch_sha256\": \"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\n        \"authenticated_owner_chain_matches\": true,\n        \"config_sha256\": \"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\n        \"current_baseline_qualification_sha256\": \"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\n        \"current_baseline_sha256\": \"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\n        \"current_executable_and_root_backing_match\": true,\n        \"current_user_namespaces_match\": true,\n        \"framework_exit_cause_resolved\": false,\n        \"historical_activation_sha256\": \"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\n        \"historical_verified_sha256\": \"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\n        \"old_helpers_and_tasks_reauthorized\": false,\n        \"previous_current_baseline_sha256\": \"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\n        \"production_ready\": false,\n        \"resource_limits_match\": true,\n        \"schema\": \"pocket4-current-main-guard-v2\",\n        \"seven_processes_match\": true,\n        \"three_host_processes_match\": true\n      },\n      \"Main_after\": {\n        \"Main_epoch_sha256\": \"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\n        \"authenticated_owner_chain_matches\": true,\n        \"config_sha256\": \"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\n        \"current_baseline_qualification_sha256\": \"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\n        \"current_baseline_sha256\": \"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\n        \"current_executable_and_root_backing_match\": true,\n        \"current_user_namespaces_match\": true,\n        \"framework_exit_cause_resolved\": false,\n        \"historical_activation_sha256\": \"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\n        \"historical_verified_sha256\": \"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\n        \"old_helpers_and_tasks_reauthorized\": false,\n        \"previous_current_baseline_sha256\": \"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\n        \"production_ready\": false,\n        \"resource_limits_match\": true,\n        \"schema\": \"pocket4-current-main-guard-v2\",\n        \"seven_processes_match\": true,\n        \"three_host_processes_match\": true\n      },\n      \"target_helper_before_after_unchanged\": true,\n      \"target_FD_closed\": 1,\n      \"held_binding_released\": true,\n      \"flow_lock_released\": true,\n      \"global_action_lock_released\": true\n    },\n    \"command005\": {\n      \"bytes\": 443,\n      \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/current-ihg877-independent-retirement-01/command-005.result.json\",\n      \"record\": {\n        \"action_attempted\": false,\n        \"automatic_retry\": false,\n        \"ended_utc\": \"2026-11-06T19:49:06.853589+00:00\",\n        \"error\": null,\n        \"errors\": [],\n        \"owned_command_joined\": true,\n        \"returncode\": 0,\n        \"seconds\": 0.0328486351063475,\n        \"spawned\": true,\n        \"stderr_sha256\": \"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\n        \"stdout_sha256\": \"bf84e8d77523a712a7b4dc5712dea5ab7e65d7c0a6c3b285eed2b30baec18b8b\",\n        \"timed_out\": false\n      },\n      \"sha256\": \"f887e2f9da435418a3c6da526efb258015a734c8b901ed29b62f0a7652c40879\"\n    },\n    \"saved_files\": [\n      {\n        \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/current-ihg877-independent-retirement-01/command-005.stdout\",\n        \"bytes\": 1963,\n        \"sha256\": \"bf84e8d77523a712a7b4dc5712dea5ab7e65d7c0a6c3b285eed2b30baec18b8b\"\n      },\n      {\n        \"path\": \"/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b/steps/current-ihg877-independent-retirement-01/before-stacks-01.txt\",\n        \"bytes\": 1963,\n        \"sha256\": \"bf84e8d77523a712a7b4dc5712dea5ab7e65d7c0a6c3b285eed2b30baec18b8b\"\n      }\n    ],\n    \"complete_parsed_roots_sha256\": \"0924224e93023e950dfc6385785df1d6ceebd66ce22a1ba6dba6ed73b6952bee\",\n    \"current_tasks\": [\n      875,\n      877,\n      878\n    ],\n    \"current_root_ids\": [\n      1,\n      877,\n      878\n    ],\n    \"preserved_current_tasks\": [\n      875,\n      878\n    ],\n    \"preserved_current_root_ids\": [\n      1,\n      878\n    ],\n    \"root_record_sha256\": {\n      \"1\": \"d7cf29998b32a57a3680dd9e3b5b1af813a2cde6216db4f376403e633cc3618a\",\n      \"877\": \"8539928b108b7b26fec241c4d3cb1ff010aa600269f78bf6c0c0e16f11f7f588\",\n      \"878\": \"d5e4b2babee582003fed221edb695fd88520f6f02f3f056f406732e9cf8efb82\"\n    },\n    \"target_component\": \"com.ihg.apps.android/com.ihg.apps.android.activity.MainActivity\",\n    \"foreign878_component\": {\n      \"bytes\": 51,\n      \"sha256\": \"c4af06acbbcc90d8d1c4d7e5e07fc9d09c20998956e86760c1b1b9231f6bb28a\",\n      \"package_is_IHG\": false\n    },\n    \"saved_file_count\": 2,\n    \"independent_prior_Android_samples\": 1,\n    \"foreign878_source_attributed\": false,\n    \"original_launch_outcome_unknown_retained\": true,\n    \"previous_retirement01_failure_retained\": true,\n    \"previous_retirement01_replayed\": false,\n    \"current_Main_requalified_by_saved_reader\": false,\n    \"cleanup_authority_created_by_saved_reader\": false\n  }\n}\n")
HISTORICAL_PARSER_SOURCE="\"\"\"Fixed historical IHG London launch007 chain and closed public error projection; no Android calls.\"\"\"\nimport ast,datetime,hashlib,json,math,os,re,stat,time\nfrom pathlib import Path\nROOT=Path('/home/alex/work/pocket4-ihg-r4-public-london-input-01')\nFLOW=Path('/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b')\nSTEP=FLOW/'steps/launch-01'\nNONCE='ec4f2977574102b1e5869d2494e8416b'\nSOURCE_SHA='24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f'\nPACKAGE='com.ihg.apps.android'\nCOMPONENT=PACKAGE+'/.activity.MainActivity'\nSCOPE_FIXED=json.loads(\"{\\\"schema\\\":\\\"pocket4-current-recorder-scope-v2\\\",\\\"current_baseline_schema\\\":\\\"pocket4-main-current-baseline-v2\\\",\\\"package\\\":\\\"com.ihg.apps.android\\\",\\\"component\\\":\\\"com.ihg.apps.android/.activity.MainActivity\\\",\\\"uid\\\":10137,\\\"user\\\":0,\\\"nonce\\\":\\\"ec4f2977574102b1e5869d2494e8416b\\\",\\\"epoch_sha256\\\":\\\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\\\",\\\"current_baseline_sha256\\\":\\\"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\\\",\\\"current_baseline_qualification_sha256\\\":\\\"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\\\",\\\"amazon_task_source_manifest_sha256\\\":\\\"24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f\\\",\\\"automatic_retry\\\":false,\\\"original_recorder_manifest_sha256\\\":\\\"002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff\\\",\\\"actual_resolution_result_sha256\\\":\\\"153ddbfc8393570621b64a478675c2a0180826a7a6ecada0ade8a6aa4ed79722\\\"}\")\nMAIN_BEFORE_FIXED=json.loads(\"{\\\"Main_epoch_sha256\\\":\\\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\\\",\\\"authenticated_owner_chain_matches\\\":true,\\\"config_sha256\\\":\\\"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\\\",\\\"current_baseline_qualification_sha256\\\":\\\"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\\\",\\\"current_baseline_sha256\\\":\\\"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\\\",\\\"current_executable_and_root_backing_match\\\":true,\\\"current_user_namespaces_match\\\":true,\\\"framework_exit_cause_resolved\\\":false,\\\"historical_activation_sha256\\\":\\\"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\\\",\\\"historical_verified_sha256\\\":\\\"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\\\",\\\"old_helpers_and_tasks_reauthorized\\\":false,\\\"previous_current_baseline_sha256\\\":\\\"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\\\",\\\"production_ready\\\":false,\\\"resource_limits_match\\\":true,\\\"schema\\\":\\\"pocket4-current-main-guard-v2\\\",\\\"seven_processes_match\\\":true,\\\"three_host_processes_match\\\":true}\")\nFILES={\n 'coordinator':ROOT/'result.json','stage':ROOT/'stage-result.json','worker':STEP/'result.json',\n 'native_intent':STEP/'command-007.intent.json','native_result':STEP/'command-007.result.json',\n 'native_stdout':STEP/'command-007.stdout','native_stderr':STEP/'command-007.stderr',\n 'scope':FLOW/'scope.json','attempted':FLOW/'launch-attempted.json',\n 'prelaunch_stacks':STEP/'prelaunch-stacks.txt','prelaunch_result':STEP/'command-006.result.json',\n 'prelaunch_stdout':STEP/'command-006.stdout','prelaunch_transport':STEP/'transport-006.verified-result.json',\n 'task_parser':Path('/home/alex/work/pocket4-current-host-r6-source-01/references/task_scope_baseline.py'),\n 'recorder_source':Path('/home/alex/work/pocket4-current-host-r6-source-01/recorder.py'),\n 'launch_scope':FLOW/'launch-scope.json'}\nLIMITS={key:65536 for key in FILES}\nLIMITS['prelaunch_stacks']=LIMITS['prelaunch_stdout']=131072\nPINS=json.loads(\"{\\\"coordinator\\\":{\\\"bytes\\\":6175,\\\"sha256\\\":\\\"09e528df22c01ffbb293264309c028ce549666602e4a97669c3eac80d62488b1\\\"},\\\"stage\\\":{\\\"bytes\\\":2187,\\\"sha256\\\":\\\"a4b5d60e30dd33ad06a4e127b6bb41c22bf7639a0c7842dd5ea6b74de5465d59\\\"},\\\"worker\\\":{\\\"bytes\\\":12051,\\\"sha256\\\":\\\"3ab8190051ab6c628a7e6b67c0f10567cb18e273db6ecc067b5856098e37034b\\\"},\\\"task_parser\\\":{\\\"bytes\\\":17281,\\\"sha256\\\":\\\"a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528\\\"},\\\"recorder_source\\\":{\\\"bytes\\\":41689,\\\"sha256\\\":\\\"c63cbdca615a609ebb41bcb25db6b770f43c4488c46a8f7b1dbee4bc462b4e64\\\"}}\")\nNATIVE_STREAMS={'stdout':'527b57dfcdb2d4a5ac88b9e3fdff8c3dda343f1d73436573131ca6886068ef8e',\n 'stderr':'8c88d864bc639295535a7e1ad3b80524162066f5179109f0bc6dfd4d25c5b6b4'}\nNATIVE_ARGV=['/usr/bin/sudo','-n','-u','#1000','--','/usr/bin/env',\n 'XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',\n '/usr/bin/droidloomctl','launch',PACKAGE,'--component',COMPONENT,'--json']\nSTACKS=['/system/bin/cmd','activity','stack','list']\nNUMBER=r'(0|[1-9][0-9]{0,12})'\nSTAGES=('control','policy','wake','snapshot','permission_resolver','activity','alias','discovery')\nCLOSED_CHILD_PATTERNS=(('backend_different_registration_ownership',\n r'task-control request failed: Backend: Android task (?P<task>[1-9][0-9]{0,9}) is already registered with different ownership'),)\ndef need(value,code):\n if not value:raise RuntimeError(code)\ndef sha(raw):return hashlib.sha256(raw).hexdigest()\ndef pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}\ndef canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()\nclass Reader:\n def __init__(self):\n  self.started=time.monotonic();self.bytes=0;self.opened=0;self.closed=0\n def opened_fd(self,fd):self.opened+=1;return fd\n def close(self,fd):\n  os.close(fd);self.closed+=1\n def maximum(self,name):\n  return LIMITS[name]\n def access(self,name,read_bytes,optional=False):\n  need(name in FILES,'EXACT_FILE_ALLOWLIST_REQUIRED')\n  path=FILES[name];maximum=self.maximum(name)\n  current=self.opened_fd(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC));fd=None\n  try:\n   try:\n    for part in path.parts[1:-1]:\n     need(time.monotonic()-self.started<8,'READ_DEADLINE')\n     nxt=self.opened_fd(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current))\n     try:self.close(current)\n     except BaseException:\n      self.close(nxt);raise\n     current=nxt\n    flags=(os.O_RDONLY if read_bytes else os.O_PATH)|os.O_NOFOLLOW|os.O_CLOEXEC\n    fd=self.opened_fd(os.open(path.name,flags,dir_fd=current))\n   except FileNotFoundError:\n    if optional:return None\n    raise\n   first=os.fstat(fd)\n   if not read_bytes:\n    return {'present':True,'regular':stat.S_ISREG(first.st_mode),'symlink':stat.S_ISLNK(first.st_mode),\n      'uid':first.st_uid,'nlink':first.st_nlink,'bytes':first.st_size,\n      'contents_read':False,'contents_qualified':False}\n   need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and 0<=first.st_size<=maximum,\n        'ROOT_SINGLE_REGULAR_SUMMARY_BOUND')\n   chunks=[];size=0\n   while True:\n    need(time.monotonic()-self.started<8,'READ_DEADLINE')\n    part=os.read(fd,min(16384,maximum+1-size))\n    if not part:break\n    chunks.append(part);size+=len(part);self.bytes+=len(part)\n    need(size<=maximum and self.bytes<=1048576,'TOTAL_READ_BOUND')\n   last=os.fstat(fd)\n   fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')\n   need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'FILE_CHANGED')\n   return b''.join(chunks)\n  finally:\n   try:\n    if fd is not None:self.close(fd)\n   finally:self.close(current)\ndef strict_json(raw):\n def pairs(items):\n  result={}\n  for key,value in items:\n   need(key not in result,'DUPLICATE_JSON_KEY')\n   result[key]=value\n  return result\n def constant(value):raise RuntimeError('NONFINITE_JSON_NUMBER')\n return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)\n\ndef utc(value):\n need(type(value) is str and re.fullmatch(r'2026-11-06T\\d{2}:\\d{2}:\\d{2}\\.\\d{6}\\+00:00',value),\n      'FIXED_DAY_UTC_TIMESTAMP_REQUIRED')\n return datetime.datetime.fromisoformat(value)\n\n\ndef safe_error(error):\n value=str(error);kind=type(error).__name__\n out={'type':kind if kind in ('RuntimeError','OSError','FileNotFoundError','PermissionError',\n     'ValueError','TypeError','JSONDecodeError','UnicodeDecodeError','KeyError') else 'other',\n     'message_sha256':sha(value.encode('utf-8','replace')),'raw_error_text_exported':False}\n if isinstance(error,RuntimeError) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}',value):out['fixed_code']=value\n if type(getattr(error,'errno',None)) is int and 0<=error.errno<=4095:out['errno']=error.errno\n return out\n\ndef classify_closed_child(error):\n matches=[]\n for name,pattern in CLOSED_CHILD_PATTERNS:\n  matched=re.fullmatch(pattern,error)\n  if matched is not None:\n   fields={}\n   for key,value in matched.groupdict().items():\n    need(re.fullmatch(r'[1-9][0-9]{0,9}',value) and int(value)<=2147483647,'CLOSED_ID_BOUND')\n    fields[key]=int(value)\n   matches.append({'shape':name,'labelled_fields':fields})\n need(len(matches)<=1,'AMBIGUOUS_CLOSED_ERROR_SHAPE')\n return matches[0] if matches else None\n\ndef public_timing_diagnostic(message):\n lines=message.split('\\n')\n first=lines[0]\n marker='droidloom-launch-timing'\n out={'line_count':len(lines),'line_metadata':[{'bytes':len(x.encode()),'sha256':sha(x.encode())} for x in lines],\n      'first_line_has_exact_outer_prefix':first.startswith('Android task launch failed (exit status: 1): '),\n      'known_timing_marker_count_in_first_line':first.count(marker),'tokens':[],\n      'unknown_token_text_exported':False,'numeric_values_are_label_bound':True}\n if first.count(marker)!=1:return out\n offset=first.index(marker);out['prefix_before_timing']={'bytes':len(first[:offset].encode()),'sha256':sha(first[:offset].encode())}\n tokens=first[offset:].split(' ')\n if len(tokens)>64:\n  out['token_bound_exceeded']=True;return out\n known={'droidloom-launch-timing','ok=false','ok=true','policy_cached=false','policy_cached=true'}\n labels=set(STAGES)|{'pending','total'}\n fields=[]\n for token in tokens:\n  item={'bytes':len(token.encode()),'sha256':sha(token.encode())}\n  if token in known:item['known_marker']=token\n  else:\n   part=re.fullmatch(r'([a-z_]+)_us=(.*)',token)\n   if part is not None and part[1] in labels:\n    item['known_time_label']=part[1]\n    item['unsigned_bounded_decimal']=re.fullmatch(NUMBER,part[2]) is not None\n    if item['unsigned_bounded_decimal']:\n     item['value_us']=int(part[2]);fields.append((part[1],int(part[2])))\n  out['tokens'].append(item)\n out['known_numeric_fields']=[{'label':k,'value_us':v} for k,v in fields]\n out['known_stage_sum_us']=sum(v for k,v in fields if k in STAGES)\n return out\n\ndef qualify_worker(c,s,w):\n need(c.get('nonce')==s.get('nonce')==w.get('nonce')==NONCE and\n  c.get('source_manifest_sha256')==s.get('source_manifest_sha256')==w.get('source_manifest_sha256')==SOURCE_SHA,\n  'EXACT_PARENT_SOURCE_NONCE')\n need(s.get('coordinator_result')=={'path':str(FILES['coordinator']),**PINS['coordinator']} and\n  c.get('retained_phase_results')=={'launch':{'path':str(FILES['worker']),**PINS['worker']}},\n  'EXACT_PARENT_CHAIN')\n for key,val in {'ok':False,'phase':'launch','package':PACKAGE,'uid':10137,\n  'helper_package':'org.droidloom.qa.ihg.r4','helper_uid':10158,'action_attempted':True,\n  'outcome_unknown':True,'automatic_retry':False,'held_binding_released':True,\n  'action_lock_released':True,'flow_lock_released':True,'source_and_artifact_unchanged':True,\n  'durable_command_count':7,'click_requests_admitted':0,'text_requests_admitted':0}.items():\n  need(type(w.get(key)) is type(val) and w[key]==val,'EXACT_FAILED_WORKER_SCOPE')\n need(w.get('secondary_errors')==[\n  {'phase':'final_Main_guard','type':'RuntimeError','message':'OWNER_SINGLE_DIRECT_CHILD_REQUIRED'},\n  {'phase':'independent_final_Main','type':'RuntimeError','message':'OWNER_SINGLE_DIRECT_CHILD_REQUIRED'}] and\n  'Main_after' not in w and 'final_Main_guard_passed' not in w,\n  'ORIGINAL_FAILED_FINAL_MAIN_MUST_REMAIN_UNKNOWN')\n need(w.get('target_FD_cleanup')=={'commercial_files_changed':False,'held_APK_FDs_closed':1} and\n  w['target_before']==w['failed_scope_files_revalidated'],'ONE_ORIGINAL_ARTIFACT_REVALIDATED')\n need(c.get('ok') is False and s.get('ok') is False and\n  c.get('launch_worker_requested') is True and c.get('inspect_worker_requested') is False and\n  c.get('cleanup_requested') is False and c.get('possible_native_launch_outcome_requires_reconciliation') is True and\n  c.get('cleanup_not_authorized_without_exact_owned_scope') is True and\n  c.get('secondary_errors')==[{'phase':'final_Main','type':'RuntimeError','message':'OWNER_SINGLE_DIRECT_CHILD_REQUIRED'}] and\n  s.get('secondary_errors')==[{'phase':'stage_final_Main','type':'RuntimeError','message':'OWNER_SINGLE_DIRECT_CHILD_REQUIRED'}] and\n  'Main_after' not in c and 'Main_after' not in s,'ORIGINAL_PARENT_FAILURE_NOT_REQUALIFIED')\n error=w.get('error')\n need(type(error) is dict and set(error)=={'phase','type','message','command_observation'} and\n  error['phase']=='one_native_launch' and error['type']=='RuntimeError' and error['message']=='COMMAND_FAILED',\n  'EXACT_NATIVE_FAILURE_LOCATION')\n original=error['command_observation']\n need(original.get('spawned') is True and original.get('owned_command_joined') is True and\n  original.get('returncode')==1 and original.get('timed_out') is False and original.get('error') is None and\n  original.get('errors')==[{'errno':None,'exception_type':'RuntimeError','phase':'post_command_guard'}] and\n  original.get('action_attempted') is True and original.get('automatic_retry') is False,\n  'EXACT_ORIGINAL_NATIVE_FAILURE_METADATA')\n for name,digest in NATIVE_STREAMS.items():need(original.get(name+'_sha256')==digest,'ORIGINAL_NATIVE_STREAM_SHA')\n maps=[c['Main_before'],s['Main_before'],w['Main_before_lock'],w['Main_before']]\n need(all(v==MAIN_BEFORE_FIXED and canon(v)==canon(MAIN_BEFORE_FIXED) for v in maps),\n  'EXACT_ORIGINAL_BEFORE_MAIN_MAPS')\n return original\ndef durable_native_result(original):\n # The pinned R6 Flow.command writes receipt before the independent post guard.\n # It then raises a copied command_observation with the later errors list.\n need(original.get('error') is None and\n  original.get('errors')==[{'errno':None,'exception_type':'RuntimeError','phase':'post_command_guard'}],\n  'EXACT_POST_WRITE_GUARD_FAILURE_REQUIRED')\n return {**original,'errors':[]}\n\ndef qualify_intent(intent,result,original):\n need(type(intent) is dict and set(intent)=={'argv','execution_argv','timeout_seconds','authority_fds_passed',\n  'mutation','label','started_utc','automatic_retry'},'EXACT_NATIVE_INTENT_FIELDS')\n need(intent['argv']==intent['execution_argv']==NATIVE_ARGV and intent['timeout_seconds']==70 and\n  intent['authority_fds_passed']==[] and intent['mutation'] is True and intent['label']=='One native launch' and\n  intent['automatic_retry'] is False,'EXACT_SINGLE_NATIVE_INTENT')\n expected=durable_native_result(original)\n need(result==expected and canon(result)==canon(expected),'NATIVE_RESULT_EQUALS_PRE_POST_GUARD_RECEIPT')\n need(utc(intent['started_utc'])<=utc(result['ended_utc']),'NATIVE_TIME_ORDER')\n return True\n\ndef qualify_scope(scope,attempted):\n need(type(scope) is dict and scope==SCOPE_FIXED and canon(scope)==canon(SCOPE_FIXED),'EXACT_TYPED_IHG_SCOPE')\n need(type(attempted) is dict and set(attempted)=={'step','time_utc','scope'} and\n  attempted['step']=='launch-01' and attempted['scope']==scope,'EXACT_NATIVE_ATTEMPT_SCOPE')\n utc(attempted['time_utc']);return True\ndef task_parser(raw):\n body=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in ('parse_stacks','exact_leaf')]\n need(len(body)==2 and {n.name for n in body}=={'parse_stacks','exact_leaf'},'EXACT_TWO_PURE_TASK_FUNCTIONS')\n env={'re':re,'require':need}\n exec(compile(ast.Module(body=body,type_ignores=[]),'<fixed-original-pure-task-functions>','exec'),env)\n return env['parse_stacks'],env['exact_leaf']\ndef task_projection(raw,roots,tasks):\n rows=[]\n for rid,root in sorted(roots.items()):\n  children=[]\n  for child in root['children']:\n   component=child['component'];pub=component==COMPONENT\n   children.append({'id':child['id'],'user':child['user'],'target_component_match':pub,\n    'component_utf8_bytes':len(component.encode()),'component_sha256':sha(component.encode()),\n    'public_target_component':COMPONENT if pub else None})\n  rows.append({'id':rid,'display':root['display'],'user':root['user'],'freeform':root['freeform'],\n   'children':children,'complete_root_record_sha256':sha(canon(root))})\n return {'raw_pin':pin(raw),'tasks':sorted(tasks),'roots':rows,'complete_parsed_roots_sha256':sha(canon(roots)),\n  'unknown_component_names_exported':False,'task_cleanup_authority_created':False}\ndef classify_native(stdout,stderr):\n out={'stdout':pin(stdout),'stderr':pin(stderr),'raw_streams_exported':False,\n  'current_installed_source_version_verified':False,'complete_wrapper_match':False,\n  'whole_error_attribution_qualified':False,'task_cleanup_authority_created':False}\n try:value=strict_json(stdout)\n except (ValueError,UnicodeError,RuntimeError):return {**out,'format':'not_complete_strict_JSON'}\n expected={'ok','host_pid','message','state'}\n if type(value) is not dict or set(value)!=expected:return {**out,'format':'other_JSON_schema'}\n if type(value['ok']) is not bool or type(value['host_pid']) is not int or type(value['state']) is not str or type(value['message']) is not str:\n  return {**out,'format':'other_JSON_field_types'}\n message=value['message'];encoded=message.encode()\n need(len(encoded)<=65536,'MESSAGE_BOUND')\n out.update(format='known_four_field_JSON',ok=value['ok'],host_pid=value['host_pid'],\n  expected_launcher_host_pid_match=value['host_pid']==3268774,\n  state=value['state'] if value['state'] in ('running','stopped','failed') else None,\n  state_sha256=sha(value['state'].encode()),message=pin(encoded),\n  stderr_exactly_repeats_complete_message=stderr==('droidloomctl: '+message+'\\n').encode(),\n  closed_word_flags={word:bool(re.search(r'(?<![A-Za-z0-9_])'+re.escape(word)+r'(?![A-Za-z0-9_])',message,re.I))\n   for word in ('failed','launch','launcher','task','registered','ownership','permission','timeout','denied','signal','crash')})\n lines=message.split('\\n')\n out['line_metadata']=[pin(line.encode()) for line in lines[:32]]\n out['line_count']=len(lines)\n out['closed_child_matches']=[]\n if len(lines)<=32:\n  for index,line in enumerate(lines):\n   prefix='droidloom-task-launcher: '\n   if line.startswith(prefix):\n    child=classify_closed_child(line[len(prefix):])\n    if child is not None:out['closed_child_matches'].append({'line_index':index,**child})\n if 0<len(encoded)<=512:out['public_timing_diagnostic']=public_timing_diagnostic(message)\n # This first read does not silently generalize any prior opaque token/message.\n return out\ndef controls(parse,exact_leaf):\n cases=[]\n def passed(name):cases.append({'name':name,'passed':True})\n def reject(name,fn):\n  try:fn()\n  except (RuntimeError,ValueError,KeyError,TypeError):passed(name);return\n  raise RuntimeError('CONTROL_ACCEPTED')\n attempt={'step':'launch-01','time_utc':'2026-11-06T11:28:18.000000+00:00','scope':dict(SCOPE_FIXED)}\n need(qualify_scope(dict(SCOPE_FIXED),attempt),'SCOPE_POSITIVE');passed('typed-scope-and-attempt-positive')\n reject('foreign-package-scope',lambda:qualify_scope({**SCOPE_FIXED,'package':'foreign.pkg'},attempt))\n reject('old-epoch-scope',lambda:qualify_scope({**SCOPE_FIXED,'epoch_sha256':'0'*64},attempt))\n reject('attempt-other-step',lambda:qualify_scope(SCOPE_FIXED,{**attempt,'step':'launch-02'}))\n reject('attempt-other-scope',lambda:qualify_scope(SCOPE_FIXED,{**attempt,'scope':{}}))\n fixture=('RootTask id=123 displayId=0 userId=0 mWindowingMode=freeform\\n'\n          '  taskId=123: SYNTHETIC_PRIVATE/.Activity bounds=[0,0][1,1] userId=0\\n').encode()\n roots,tasks=parse(fixture.decode());need(tasks=={123},'TASK_FIXTURE')\n safe=task_projection(fixture,roots,tasks)\n need('SYNTHETIC_PRIVATE' not in json.dumps(safe),'TASK_TEXT_LEAK');passed('original-task-parser-safe-summary')\n reject('duplicate-task-rejected',lambda:parse((fixture+fixture).decode()))\n reject('unparsed-task-rejected',lambda:parse('RootTask id=123 displayId=0 userId=0\\n taskId=invalid\\n'))\n child='task-control request failed: Backend: Android task 123 is already registered with different ownership'\n need(classify_closed_child(child)=={'shape':'backend_different_registration_ownership','labelled_fields':{'task':123}},'CLOSED_CHILD')\n passed('exact-public-child-shape')\n need(classify_closed_child(child+' UNKNOWN') is None,'CLOSED_FULLMATCH');passed('child-suffix-not-accepted')\n raw=canon({'ok':False,'host_pid':3268774,'state':'running','message':'SYNTHETIC_PRIVATE message'})\n p=classify_native(raw,b'private mismatch')\n need('SYNTHETIC_PRIVATE' not in json.dumps(p) and not p['stderr_exactly_repeats_complete_message'] and\n  p['whole_error_attribution_qualified'] is False,'MESSAGE_PRIVACY')\n passed('unknown-message-hash-only-no-attribution')\n reject('duplicate-JSON-key',lambda:strict_json(b'{\"x\":1,\"x\":2}'))\n need(len(cases)==12,'EXACT_TWELVE_CONTROLS');return cases\ndef receipt_controls(c,s,w):\n cases=[]\n def passed(name):cases.append({'name':name,'passed':True})\n def reject(name,fn):\n  try:fn()\n  except (RuntimeError,ValueError,KeyError,TypeError):passed(name);return\n  raise RuntimeError('RECEIPT_CONTROL_ACCEPTED')\n original=qualify_worker(c,s,w)\n need(original['errors']==[{'errno':None,'exception_type':'RuntimeError','phase':'post_command_guard'}] and\n  w['outcome_unknown'] is True,'ACTUAL_FAILURE_PRESERVED')\n passed('actual-pinned-failed-worker-retains-post-guard-and-unknown')\n intent={'argv':list(NATIVE_ARGV),'execution_argv':list(NATIVE_ARGV),'timeout_seconds':70,\n  'authority_fds_passed':[],'mutation':True,'label':'One native launch',\n  'started_utc':'2026-11-06T17:40:00.000000+00:00','automatic_retry':False}\n recorded=durable_native_result(original)\n need(qualify_intent(intent,recorded,original),'DURABLE_WRITE_ORDER_POSITIVE')\n passed('durable-result-before-post-guard-exact-positive')\n reject('worker-previous-source-rejected',lambda:qualify_worker(c,s,{**w,'source_manifest_sha256':'0'*64}))\n rejected=strict_json(canon(w));rejected['error']['command_observation']['errors']=[]\n reject('worker-missing-post-guard-error-rejected',lambda:qualify_worker(c,s,rejected))\n reject('durable-stream-hash-change-rejected',\n  lambda:qualify_intent(intent,{**recorded,'stdout_sha256':'0'*64},original))\n reject('later-post-guard-error-cannot-be-in-original-durable-receipt',\n  lambda:qualify_intent(intent,original,original))\n reject('later-diagnostic-main-cannot-fill-original-after',\n  lambda:qualify_worker(c,s,{**w,'Main_after':dict(MAIN_BEFORE_FIXED),'final_Main_guard_passed':True}))\n need(len(cases)==7,'EXACT_SEVEN_RECEIPT_CONTROLS')\n return cases\n\ndef collect():\n need(os.getuid()==os.geteuid()==0,'ROOT_FIXED_READ_ONLY')\n r=Reader();observations={};bindings={};errors=[];native=None;prelaunch=None;safe_attempt=None;tests=[]\n def get(name,expected=None):\n  raw=r.access(name,True)\n  if expected is not None:need(pin(raw)==expected,'FIXED_ORIGINAL_PIN_CHANGED')\n  observations[name]={'path':str(FILES[name]),**pin(raw)};return raw\n try:\n  fixed={name:get(name,p) for name,p in PINS.items()}\n  c,s,w=(strict_json(fixed[k]) for k in ('coordinator','stage','worker'))\n  original=qualify_worker(c,s,w)\n  parse,exact_leaf=task_parser(fixed['task_parser']);tests=controls(parse,exact_leaf)+receipt_controls(c,s,w)\n  need(len(tests)==19,'EXACT_NINETEEN_CONTROLS')\n  intent_raw=get('native_intent');result_raw=get('native_result')\n  intent,result=strict_json(intent_raw),strict_json(result_raw)\n  qualify_intent(intent,result,original);bindings['native_intent_and_durable_pre_post_guard_result_exact']=True\n  bindings['original_post_command_guard_failure_retained']=True\n  streams={name:get('native_'+name) for name in ('stdout','stderr')}\n  for name,raw in streams.items():need(sha(raw)==NATIVE_STREAMS[name],'NATIVE_STREAM_BOUND_TO_WORKER')\n  native=classify_native(streams['stdout'],streams['stderr']);bindings['native_streams_exact']=True\n  scope_raw,attempt_raw=get('scope'),get('attempted')\n  scope,attempt=strict_json(scope_raw),strict_json(attempt_raw)\n  qualify_scope(scope,attempt);bindings['scope_and_attempt_exact_source']=True\n  safe_attempt={'step':attempt['step'],'time_utc':attempt['time_utc'],'scope':scope}\n  raw=get('prelaunch_stacks');recorded=get('prelaunch_stdout')\n  pr=strict_json(get('prelaunch_result'));transport=strict_json(get('prelaunch_transport'))\n  need(raw==recorded and pr.get('stdout_sha256')==sha(raw) and pr.get('stderr_sha256')==sha(b'') and\n   pr.get('returncode')==0 and pr.get('spawned') is True and pr.get('owned_command_joined') is True and\n   pr.get('timed_out') is False and pr.get('error') is None and pr.get('errors')==[] and\n   pr.get('action_attempted') is False and pr.get('automatic_retry') is False,'PRELAUNCH_JOINED_READ_ONLY')\n  command_sha=sha(json.dumps(STACKS,separators=(',',':')).encode())\n  need(transport.get('sequence')==6 and transport.get('epoch_sha256')==SCOPE_FIXED['epoch_sha256'] and\n   transport.get('package')==PACKAGE and transport.get('uid')==10137 and transport.get('command_sha256')==command_sha and\n   transport.get('returncode')==0 and transport.get('stdout_sha256')==sha(raw) and\n   transport.get('stdout_bytes')==len(raw) and transport.get('stderr_bytes')==0 and\n   transport.get('stderr_sha256')==sha(b'') and transport.get('outcome_unknown') is False and\n   transport.get('automatic_retry') is False and transport.get('numeric_pid_target_used') is False,\n   'PRELAUNCH_VERIFIED_HELD_STACKS_ONLY')\n  need(utc(pr['ended_utc'])<=utc(attempt['time_utc'])<=utc(intent['started_utc'])<=utc(result['ended_utc']),\n   'HISTORICAL_SEQUENCE_ORDER')\n  roots,tasks=parse(raw.decode('utf-8','strict'))\n  need(not any(child['component'].split('/')[0]==PACKAGE for root in roots.values() for child in root['children']),\n   'NO_PREEXISTING_TARGET_BASELINE')\n  prelaunch=task_projection(raw,roots,tasks);bindings['prelaunch_exact_source_command_and_complete_original_parser']=True\n  meta=r.access('launch_scope',False,optional=True)\n  observations['launch_scope_metadata']=meta if meta is not None else {'present':False,'contents_read':False}\n  need(meta is None,'ORIGINAL_SUCCESS_SCOPE_MUST_REMAIN_ABSENT')\n  bindings['original_success_scope_absent']=True\n except BaseException as error:errors.append(safe_error(error))\n finally:\n  if r.opened!=r.closed:errors.append({'fixed_code':'READER_FD_CLOSE_NOT_COMPLETE'})\n out={'schema':'pocket4-fixed-ihg-london-native-launch007-chain-v1','ok':not errors,'source_sha256':SOURCE_SHA256,\n  'observations':observations,'bindings':bindings,'native_projection':native,\n  'scope_and_attempt':safe_attempt,'prelaunch':prelaunch,'controls':tests,'control_count':len(tests),\n  'errors':errors,'file_descriptors_opened':r.opened,'file_descriptors_closed':r.closed,\n  'bytes_read':r.bytes,'historical_launch_outcome_unknown_retained':True,'private_UI_read':False,\n  'raw_native_message_or_unknown_task_text_exported':False,'original_files_modified':0,\n  'Android_commands':0,'UI_actions':0,'processes_spawned':0,'task_cleanup_authorized':False,\n  'current_task_state_observed':False,'current_Main_requalified':False,\n  'original_post_command_Main_failure_retained':True,'current_installed_source_version_verified':False,\n  'whole_app_production_ready':False}\n data=(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\\n').encode()\n need(len(data)<=65536,'SAFE_SUMMARY_BOUND')\n print(data.decode(),end='',flush=True);return 0 if out['ok'] else 1\n"
HISTORICAL_PARSER_PIN={"bytes":27352,"sha256":"01efab63ac15390b9a67863ba80eb489e4f2961e47fc00bc0e1a6f6a73bbec2d"}
OWNED_CONTEXT_SOURCE="\"\"\"Explicit current IHG task retirement context; original source remains frozen.\"\"\"\nimport json,math,os,stat,time\nfrom pathlib import Path\nPACKAGE='com.ihg.apps.android'\nUID=10137\nTASK=877\nCOMPONENT=PACKAGE+'/'+PACKAGE+'.activity.MainActivity'\nSCHEMA='pocket4-independent-current-IHG-task-retirement-scope-v1'\ndef need(value,code):\n if not value:raise RuntimeError(code)\ndef validate_retirement_scope(value,source_sha):\n fields={'schema','task','component','package','uid','user','epoch_sha256','baseline_sha256',\n  'qualification_sha256','source_sha256','prelaunch_absent','cleanup_allowed',\n  'independent_current_scope','original_launch_outcome','original_launch_scope_created',\n  'authorizes_original_action_replay','native_reported_task_id'}\n need(type(value) is dict and set(value)==fields and value['schema']==SCHEMA and\n  type(value['task']) is int and value['task']==TASK and value['component']==COMPONENT and\n  value['package']==PACKAGE and value['uid']==10137 and value['user']==0 and\n  value['epoch_sha256']=='7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c' and\n  value['baseline_sha256']=='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364' and\n  value['qualification_sha256']=='ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e' and\n  value['source_sha256']==source_sha and value['prelaunch_absent'] is True and value['cleanup_allowed'] is True and\n  value['independent_current_scope'] is True and value['original_launch_outcome']=='unknown_retained' and\n  value['original_launch_scope_created'] is False and value['authorizes_original_action_replay'] is False and\n  value['native_reported_task_id'] is None,'EXACT_NEW_INDEPENDENT_IHG877_SCOPE')\n return True\ndef make_flow_type(task,bound_scope,source_sha):\n validate_retirement_scope(bound_scope,source_sha)\n frozen_scope=json.loads(json.dumps(bound_scope))\n class IndependentRetirementFlow(task.Flow):\n  \"\"\"An owned subclass, never a mutation of the original module or Policy.\"\"\"\n  def __init__(self,**options):\n   need(options.get('phase')=='cleanup','ONLY_CURRENT_RETIREMENT_PHASE')\n   super().__init__(**options)\n   self.retirement_authority=None;self.retirement_counts={};self.retirement_remove_attempted=False\n  def arm_after_exact_pair(self,first_roots,first_tasks,second_roots,second_tasks,preserved_roots,preserved_tasks):\n   self.guard()\n   need(self.command_index==6 and self.retirement_counts==self.policy.counts==\n    {'target_uid':1,'target_path':1,'helper_uid':1,'helper_path':1,'stacks':2} and\n    self.action_attempted is False and not self.launch_claimed and self.retirement_authority is None,\n    'SIX_PRIOR_CURRENT_READS_BEFORE_RETIREMENT_ARM')\n   need(first_roots==second_roots and first_tasks==second_tasks and\n    set(second_tasks)-{TASK}==set(preserved_tasks) and set(second_roots)-{TASK}==set(preserved_roots) and\n    all(second_roots.get(k)==v for k,v in preserved_roots.items()) and\n    TASK not in preserved_tasks and TASK not in preserved_roots and\n    self.tasks.exact_leaf(second_roots,TASK,PACKAGE) and\n    second_roots[TASK]['children']==[{'id':TASK,'component':COMPONENT,'user':0}],\n    'TWO_COMPLETE_CURRENT_TABLES_AND_EXACT_IHG877_LEAF')\n   self.retirement_authority=json.loads(json.dumps(frozen_scope))\n  def selected_task(self):\n   need(self.retirement_authority==frozen_scope,'NEW_RETIREMENT_SCOPE_NOT_ARMED')\n   validate_retirement_scope(self.retirement_authority,source_sha)\n   return dict(self.retirement_authority)\n  def android(self,argv,timeout=20,*,mutation=False):\n   need(type(argv) is list and all(type(x) is str for x in argv) and type(mutation) is bool and\n    type(timeout) in (int,float) and math.isfinite(timeout),\n    'EXACT_INDEPENDENT_RETIREMENT_COMMAND_SHAPE')\n   allowed={tuple(task.LIST):('target_uid',15,2),tuple(task.PATHS):('target_path',15,2),\n    tuple(task.OWN_UID):('helper_uid',8,2),tuple(task.OWN_PATH):('helper_path',8,2)}\n   if tuple(argv) in allowed:\n    key,expected,limit=allowed[tuple(argv)]\n    need(mutation is False and timeout==expected,'CURRENT_RETIREMENT_METADATA_ONLY')\n   elif argv==task.STACKS:\n    key,limit='stacks',33\n    need(mutation is False and 0<timeout<=20,'CURRENT_RETIREMENT_STACK_READ_ONLY')\n   else:\n    need(argv==['/system/bin/cmd','activity','stack','remove',str(TASK)] and timeout==20 and mutation is True,\n     'ONLY_EXACT_IHG877_REMOVE')\n    self.selected_task()\n    need(not self.retirement_remove_attempted and self.command_index==6,'SINGLE_REMOVE_AFTER_FRESH_PAIR')\n    self.retirement_remove_attempted=True;key,limit='remove',1\n   used=self.retirement_counts.get(key,0);need(used<limit,'INDEPENDENT_RETIREMENT_COMMAND_LIMIT')\n   self.retirement_counts[key]=used+1\n   # Original Policy.admit, BoundArun, held runner, guard and poison semantics remain active.\n   return super().android(argv,timeout,mutation=mutation)\n  def command(self,*args,**kwargs):raise RuntimeError('NATIVE_LAUNCH_FORBIDDEN_IN_INDEPENDENT_RETIREMENT')\n  def launch_locked(self):raise RuntimeError('NATIVE_LAUNCH_FORBIDDEN_IN_INDEPENDENT_RETIREMENT')\n  def cleanup(self):raise RuntimeError('ORIGINAL_LAUNCH_SCOPE_CLEANUP_FORBIDDEN')\n return IndependentRetirementFlow\n\ndef open_independent_context(task,flow_type,ref,util,context,source_manifest,source_verify,flow_root,step,\n                      transport,result,deadline,phase,qa,inspect_plan,resolve,expected_scope, *,\n                      install_source_manifest):\n    \"\"\"Same held Main/classpath primitives as the qualified Amazon install.\n\n    The only newly constructed object is the phase-restricted task Flow above.\n    No original Bili Flow/MainBinding or old UI client constructor is called.\n    \"\"\"\n    source=util.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,\n                       'amazon_task_shared_contract')\n    contract=source.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)\n    recorder=contract.load('recorder.py','amazon_task_actual_command')\n    held=contract.load('references/held_runtime_r5.py','amazon_task_actual_held_main')\n    binding=contract.load('main_binding.py','amazon_task_shared_classpath_only')\n    activation=ref.current_baseline()\n    own_scope=context.baseline_scope(ref,activation)\n    epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,\n                     'amazon_task_fixed_epoch')\n    scope_raw=util.read(flow_root/'scope.json',65536)\n    scope=json.loads(scope_raw)\n    task.current_task_scope(scope,qa,contract)\n    need(scope==expected_scope and all(scope[key]==value for key,value in own_scope.items()),\n         'EXACT_NEW_CURRENT_IHG_FLOW_SCOPE_REQUIRED')\n    need(util.read(flow_root/'baseline.json',expected=ref.BASELINE_SHA)==ref.read(ref.BASELINE,expected=ref.BASELINE_SHA)\n         and util.read(flow_root/'baseline-qualification.json',expected=ref.QUALIFICATION_SHA)==ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA),\n         'SAVED_TYPED_CURRENT_BASELINE_CHANGED')\n    info=flow_root.lstat()\n    need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o077,\n         'PRIVATE_ROOT_OWNED_NEW_FLOW_REQUIRED')\n    target=None\n    def guard():\n        need(time.monotonic()<deadline,'AMAZON_PHASE_DEADLINE')\n        source_verify(source_manifest);contract.verify()\n        need(util.read(flow_root/'scope.json',65536)==scope_raw,'AMAZON_SCOPE_CHANGED')\n        ref.read(recorder.APP,expected=recorder.APP_SHA)\n        util.read(source.HELPER_PATH,source.HELPER_BYTES,source.HELPER_SHA,source.HELPER_BYTES)\n        observation=ref.main_guard(activation,epoch)\n        if target is not None:context.verify_target_data(target,activation,binding)\n        return observation\n    result['Main_before']=guard();result['shared_helper']=source.verify_shared_helper()\n    expected=activation['framework_epoch']['binding']['processes']['init']\n    proc=os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)\n    try:actual=held.proc_identity_at(proc,expected['host_pid'],time.monotonic()+3)\n    finally:os.close(proc)\n    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')\n    try:\n        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA);guard()\n        app=util.module(Path(recorder.APP),recorder.APP_SHA,'amazon_task_discovery_only')\n        init,discovered,status=context.current_discovery(\n            util,install_source_manifest,util.verify_source,util.HERE,\n            app,activation,epoch,guard)\n        need(init==expected['host_pid'] and status['host_pid']==activation['status']['host_pid'],\n             'FIXED_MAIN_DISCOVERY_CHANGED')\n        values,classpath=binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)\n        need(all(discovered.get(k)==v for k,v in values.items()),'CLASSPATH_DISCOVERY_CHANGED')\n        environment=transport.environment_values(discovered)\n        tasks=recorder.task_functions(context.INSTALLED_SHARED/'references/task_scope_baseline.py')\n        flow=flow_type(recorder=recorder,contract=contract,target=target,environment=environment,\n            transport=transport,main_guard=guard,root=flow_root,step=step,phase=phase,\n            scope=scope,activation=activation,tasks=tasks,qa=qa,inspect_plan=inspect_plan,\n            resolve=resolve,read=util.read,deadline=deadline)\n        ref.write_new(step/'held-main-binding.json',{'target':target.record,'classpath':classpath,\n            'shared_helper':result['shared_helper'],'target_package':PACKAGE,'target_uid':UID,\n            'shared_recorder_primitive_manifest':context.SHARED_MANIFEST,\n            'amazon_task_runtime_source_manifest':source_manifest,'Bili_Flow_instantiated':False})\n        return flow,recorder,lambda:ref.main_guard(activation,epoch)\n    except BaseException as primary:\n        if target is not None:\n            try:target.close()\n            except BaseException as secondary:primary.add_note('held target close: '+repr(secondary))\n        raise\n"
OWNED_CONTEXT_PIN={"bytes":10020,"sha256":"5aa84393992f76ef04f781dcbb141a9f1cf84d544f9556d89055921d934a9fd3"}

"""One independently authorized current IHG877 retirement; original London failure remains unknown."""
import datetime,hashlib,json,math,os,re,stat,time,types
from pathlib import Path
ROOT=Path('/home/alex/work/pocket4-ihg-r4-public-london-input-01')
SOURCE=ROOT/'source'
FLOW=Path('/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b')
STEP_NAME='current-ihg877-independent-retirement-02'
STEP=FLOW/'steps'/STEP_NAME
MARKER=STEP/'remove-attempted.json'
RECONCILIATION=STEP/'independent-current-retirement.json'
PACKAGE='com.ihg.apps.android'
COMPONENT=PACKAGE+'/'+PACKAGE+'.activity.MainActivity'
TASK=877
SOURCE_MANIFEST='24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f'
ENTRY_PIN={'bytes':46630,'sha256':'562629c6c00d40a41cdf6fe2edf3df01292fb6f78409f8fd08b7776f02bf7bb0'}
def need(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
def canon(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
MAIN_BEFORE_FIXED=json.loads("{\"Main_epoch_sha256\":\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\"authenticated_owner_chain_matches\":true,\"config_sha256\":\"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\"current_baseline_qualification_sha256\":\"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\"current_baseline_sha256\":\"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\"current_executable_and_root_backing_match\":true,\"current_user_namespaces_match\":true,\"framework_exit_cause_resolved\":false,\"historical_activation_sha256\":\"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\"historical_verified_sha256\":\"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\"old_helpers_and_tasks_reauthorized\":false,\"previous_current_baseline_sha256\":\"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\"production_ready\":false,\"resource_limits_match\":true,\"schema\":\"pocket4-current-main-guard-v2\",\"seven_processes_match\":true,\"three_host_processes_match\":true}")

def read_exact(path,expected,maximum=65536):
 need(type(expected) is dict and set(expected)=={'bytes','sha256'} and type(expected['bytes']) is int and
  0<=expected['bytes']<=maximum,'EXACT_FILE_PIN_REQUIRED')
 current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
 try:
  for part in path.parts[1:-1]:
   nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
   try:os.close(current)
   except BaseException:
    os.close(nxt);raise
   current=nxt
  fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
  first=os.fstat(fd)
  need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and first.st_size==expected['bytes'],
   'ROOT_SINGLE_REGULAR_EXACT_INPUT')
  chunks=[];size=0
  while True:
   part=os.read(fd,min(65536,maximum+1-size))
   if not part:break
   size+=len(part);chunks.append(part);need(size<=maximum,'READ_BOUND')
  last=os.fstat(fd)
  fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
  need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'EXACT_FILE_CHANGED')
  raw=b''.join(chunks);need(pin(raw)==expected,'EXACT_FILE_SHA');return raw
 finally:
  try:
   if fd is not None:os.close(fd)
  finally:os.close(current)

def summary(roots,tasks):
 need(0<len(roots)<=512 and 0<len(tasks)<=512,'CURRENT_TASK_COUNT_BOUND')
 rows=[]
 for rid,root in sorted(roots.items()):
  need(type(rid) is int and 0<rid<2147483648 and
       type(root['display']) is int and 0<=root['display']<2147483648 and
       type(root['user']) is int and 0<=root['user']<2147483648,'ROOT_METADATA_BOUND')
  children=[]
  for child in root['children']:
   need(type(child['id']) is int and 0<child['id']<2147483648 and
        type(child['user']) is int and 0<=child['user']<2147483648,'TASK_METADATA_BOUND')
   children.append({'task_id':child['id'],'user':child['user'],
    'is_target_package':child['component'].split('/')[0]==PACKAGE,
    'is_exact_target_component':child['component']==COMPONENT})
  rows.append({'root_id':rid,'display_id':root['display'],'user':root['user'],
      'freeform':root['freeform'],'children':children})
 return {'task_ids':sorted(tasks),'roots':rows}

def owned_command_record(number):
 need(type(number) is int and 1<=number<=42,'FIXED_RETIREMENT_COMMAND_INDEX')
 path=FLOW/'steps'/STEP_NAME/('command-%03d.result.json'%number)
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  first=os.fstat(fd)
  need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
       0<first.st_size<=8192,'OWNED_COMMAND_RECORD_SHAPE')
  raw=os.read(fd,8193);last=os.fstat(fd)
  keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
  need(len(raw)==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),
       'OWNED_COMMAND_RECORD_CHANGED')
 finally:os.close(fd)
 v=json.loads(raw)
 need(type(v) is dict and set(v)=={'ended_utc','seconds','returncode','timed_out','spawned','error',
      'errors','owned_command_joined','stdout_sha256','stderr_sha256','action_attempted','automatic_retry'},
      'EXACT_ORIGINAL_COMMAND_METADATA')
 need(type(v['ended_utc']) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00',v['ended_utc']) and
      type(v['seconds']) in (int,float) and 0<=v['seconds']<=90 and
      (v['returncode'] is None or type(v['returncode']) is int) and
      all(type(v[k]) is bool for k in ('timed_out','spawned','owned_command_joined','action_attempted','automatic_retry')) and
      all(type(v[k]) is str and re.fullmatch('[0-9a-f]{64}',v[k]) for k in ('stdout_sha256','stderr_sha256')),
      'FIXED_COMMAND_SCALAR_TYPES')
 need(type(v['errors']) is list and len(v['errors'])<=32 and
      v['error']==(v['errors'][0] if v['errors'] else None),'FIXED_COMMAND_FIRST_ERROR')
 for e in v['errors']:
  need(type(e) is dict and set(e)=={'phase','exception_type','errno'} and
       e['phase'] in ('command_wait','owned_command_group_stop','owned_command_join',
       'command_spawn_or_wait','command_output_open','command_output_sync','command_output_close',
       'command_output_read','command_result_record','post_command_guard') and
       type(e['exception_type']) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}',e['exception_type']) and
       (e['errno'] is None or type(e['errno']) is int),'FIXED_COMMAND_ERROR_METADATA')
 return {'path':str(path),'bytes':len(raw),'sha256':sha(raw),'record':v}

def qualify_joined_command(record,raw,mutation):
 need(type(mutation) is bool and isinstance(raw,bytes),'EXACT_COMMAND_OUTPUT_KIND')
 need(record['returncode']==0 and record['spawned'] is True and
      record['owned_command_joined'] is True and record['timed_out'] is False and
      record['error'] is None and record['errors']==[] and
      record['action_attempted'] is mutation and record['automatic_retry'] is False and
      record['stdout_sha256']==sha(raw) and record['stderr_sha256']==sha(b''),
      'EXACT_JOINED_QUIET_RETIREMENT_COMMAND')
 return True

def command_gate_controls():
 rows=[];raw=b'fixed synthetic result\n'
 base={'returncode':0,'spawned':True,'owned_command_joined':True,'timed_out':False,
       'error':None,'errors':[],'action_attempted':False,'automatic_retry':False,
       'stdout_sha256':sha(raw),'stderr_sha256':sha(b'')}
 need(qualify_joined_command(base,raw,False),'CONTROL_JOINED_READ')
 rows.append({'name':'joined_read_positive','passed':True})
 need(qualify_joined_command({**base,'action_attempted':True},raw,True),'CONTROL_JOINED_REMOVE')
 rows.append({'name':'joined_remove_positive','passed':True})
 bad=[
  ('nonzero_rc',{'returncode':1}),
  ('not_joined',{'owned_command_joined':False}),
  ('timeout',{'timed_out':True}),
  ('metadata_error',{'error':{'phase':'fixture'},'errors':[{'phase':'fixture'}]}),
  ('changed_stdout',{'stdout_sha256':'0'*64}),
  ('nonempty_stderr',{'stderr_sha256':sha(b'not empty')}),
  ('wrong_mutation_flag',{'action_attempted':True}),
  ('automatic_retry',{'automatic_retry':True})]
 for name,change in bad:
  try:qualify_joined_command({**base,**change},raw,False)
  except RuntimeError:rows.append({'name':name,'passed':True})
  else:raise RuntimeError('COMMAND_GATE_NEGATIVE_ACCEPTED_'+name.upper())
 need(len(rows)==10,'COMMAND_GATE_CONTROL_COUNT')
 return rows

def safe_error(error):
 name=type(error).__name__;message=str(error)
 value={'exception_type':name if name in ('RuntimeError','OSError','PermissionError','FileNotFoundError',
  'ValueError','KeyError','TypeError','TimeoutError') else 'other',
  'message_sha256':sha(message.encode('utf-8','replace')),'raw_message_exported':False}
 if isinstance(error,RuntimeError) and re.fullmatch('[A-Z][A-Z0-9_]{0,127}',message):
  value['fixed_code']=message
 if type(getattr(error,'errno',None)) is int:value['errno']=error.errno
 return value

def qualify_task_set(roots,tasks,baseline_roots,baseline_tasks,task,exact_leaf):
 need(type(task) is int and 0<task<=2147483647,'EXACT_POSITIVE_RECONCILIATION_TASK')
 need(task not in baseline_tasks and task not in baseline_roots,'PREEXISTING_TASK_NEVER_RETIRE')
 need(set(tasks)-{task}==set(baseline_tasks),'OTHER_TASK_SET_CHANGED')
 need(set(roots)-{task}==set(baseline_roots),'OTHER_ROOT_SET_CHANGED')
 need(all(roots.get(k)==v for k,v in baseline_roots.items()),'PREEXISTING_ROOT_CONTENT_CHANGED')
 if task not in tasks and task not in roots:
  return {'status':'already_absent','removal_allowed':False}
 need(task in tasks and task in roots,'INCOMPLETE_TARGET_ROOT_TASK_PAIR')
 need(exact_leaf(roots,task,PACKAGE),'RECONCILIATION_NOT_EXACT_OWNED_LEAF')
 need(roots[task]['children'][0]['component']==COMPONENT,'EXACT_TARGET_COMPONENT_REQUIRED')
 return {'status':'exact_live_leaf','removal_allowed':True}

def task_set_controls(exact_leaf):
 rows=[]
 def passed(name,value):need(value,'TASK_GATE_CONTROL_'+name.upper());rows.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name,True);return
  raise RuntimeError('TASK_GATE_CONTROL_ACCEPTED_'+name.upper())
 base={1:{'display':0,'user':0,'freeform':False,
  'children':[{'id':875,'user':0,'component':'fixture.system/Fixture'}]}}
 target={'display':0,'user':0,'freeform':True,
  'children':[{'id':877,'user':0,'component':COMPONENT}]}
 def qualify(roots,tasks):return qualify_task_set(roots,tasks,base,{875},877,exact_leaf)
 passed('exact_live_leaf',qualify({**base,877:target},{875,877})=={'status':'exact_live_leaf','removal_allowed':True})
 passed('already_absent',qualify(base,{875})=={'status':'already_absent','removal_allowed':False})
 rejected('preserved_task_missing',lambda:qualify({877:target},{877}))
 rejected('unrelated_new_task',lambda:qualify({**base,877:target},{875,877,878}))
 rejected('unrelated_new_root',lambda:qualify({**base,877:target,878:target},{875,877}))
 rejected('foreign_component',lambda:qualify({**base,877:{**target,'children':[{'id':877,'user':0,'component':'other.app/Main'}]}},{875,877}))
 rejected('wrong_same_package_component',lambda:qualify({**base,877:{**target,'children':[{'id':877,'user':0,'component':PACKAGE+'/Other'}]}},{875,877}))
 rejected('wrong_display',lambda:qualify({**base,877:{**target,'display':1}},{875,877}))
 rejected('wrong_user',lambda:qualify({**base,877:{**target,'user':1}},{875,877}))
 rejected('non_leaf',lambda:qualify({**base,877:{**target,'children':target['children']+[{'id':878,'user':0,'component':COMPONENT}]}},{875,877}))
 rejected('task_without_root',lambda:qualify(base,{875,877}))
 rejected('preexisting_target_id',lambda:qualify_task_set(base,{875},base,{875},875,exact_leaf))
 need(len(rows)==12,'TASK_GATE_CONTROL_COUNT')
 return rows

def current_read_plans(entry):
 # Exact shape used by the fixed production worker, even for phase='launch'.
 search_plan=json.loads(json.dumps(entry.SEARCH_PLAN));click_plan=json.loads(json.dumps(entry.PLAN))
 input_plan=json.loads(json.dumps(entry.INPUT_PLAN))
 post_plan=json.loads(json.dumps(entry.POST_PLAN));readiness_plans=json.loads(json.dumps(entry.SEARCH_READINESS_PLANS))
 return {'search':search_plan,'destination':click_plan,'input':input_plan,'post':post_plan,'readiness':readiness_plans}

def current_main_read_window(result):
 keys=('Main_before_lock','Main_after_locks','Main_after')
 sampled=[key for key in keys if key in result]
 need('Main_after' in sampled,'INDEPENDENT_FINAL_MAIN_SAMPLE_REQUIRED')
 need(all(type(result[key]) is dict and result[key]==MAIN_BEFORE_FIXED for key in sampled),
  'MAIN_READ_WINDOW_CHANGED')
 return {'sampled_fields':sampled,'all_available_samples_equal':True,'complete':sampled==list(keys),
  'historical_Main_fields_used':False,'missing_samples_filled':False}

def current_main_window_controls():
 cases=[]
 incomplete={'Main_before_lock':dict(MAIN_BEFORE_FIXED),'Main_after':dict(MAIN_BEFORE_FIXED)}
 observed=current_main_read_window(incomplete)
 need(observed=={'sampled_fields':['Main_before_lock','Main_after'],'all_available_samples_equal':True,
  'complete':False,'historical_Main_fields_used':False,'missing_samples_filled':False} and
  'Main_after_locks' not in incomplete,'EARLY_FAILURE_RETAINS_INCOMPLETE_CURRENT_WINDOW')
 cases.append({'name':'early-failure-equal-current-samples-incomplete-without-false-drift','passed':True})
 complete={key:dict(MAIN_BEFORE_FIXED) for key in ('Main_before_lock','Main_after_locks','Main_after')}
 need(current_main_read_window(complete)['complete'] is True,'COMPLETE_CURRENT_MAIN_WINDOW')
 cases.append({'name':'three-actual-current-samples-required-for-complete-window','passed':True})
 for key in ('Main_after_locks','Main_after'):
  changed={name:dict(value) for name,value in complete.items()}
  changed[key]['Main_epoch_sha256']='0'*64
  try:current_main_read_window(changed)
  except RuntimeError as error:
   need(str(error)=='MAIN_READ_WINDOW_CHANGED','WRONG_CURRENT_MAIN_DRIFT_REJECTION')
   cases.append({'name':'sampled-'+key+'-drift-rejected','passed':True});continue
  raise RuntimeError('CURRENT_MAIN_DRIFT_ACCEPTED')
 need(len(cases)==4,'EXACT_FOUR_CURRENT_MAIN_WINDOW_CONTROLS')
 return cases

"""Private historical chain qualification for a new current IHG877 retirement scope."""
def verify_historical(hist,inputs,read_exact,qualify_joined_command):
 need(inputs['schema']=='pocket4-independent-current-IHG877-retirement-input-v1' and inputs['task']==TASK and
  inputs['package']==PACKAGE and inputs['component']==COMPONENT and
  inputs['original_launch_outcome']=='unknown_retained' and inputs['native_reported_task_id'] is None and
  inputs['old_task876_disappearance_attributed'] is False,'EXACT_CURRENT_RETIREMENT_INPUTS')
 r=hist.Reader();observed={};primary=None
 def get(name):
  expected=inputs['fixed_historical_files'][name]
  need(expected['path']==str(hist.FILES[name]),'EXACT_HISTORICAL_ALLOWLIST_PATH')
  raw=r.access(name,True);p={'bytes':expected['bytes'],'sha256':expected['sha256']}
  need(pin(raw)==p,'FIXED_HISTORICAL_ORIGINAL_CHANGED')
  observed[name]={'path':expected['path'],**p};return raw
 try:
  fixed={name:get(name) for name in hist.PINS}
  c,s,w=(hist.strict_json(fixed[k]) for k in ('coordinator','stage','worker'))
  original=hist.qualify_worker(c,s,w)
  parse,exact_leaf=hist.task_parser(fixed['task_parser'])
  intent=hist.strict_json(get('native_intent'));native_result=hist.strict_json(get('native_result'))
  hist.qualify_intent(intent,native_result,original)
  streams={name:get('native_'+name) for name in ('stdout','stderr')}
  for name,raw in streams.items():need(sha(raw)==hist.NATIVE_STREAMS[name],'ORIGINAL_NATIVE_STREAM_SHA')
  projection=hist.classify_native(streams['stdout'],streams['stderr'])
  need(projection==inputs['native_projection'] and projection['closed_child_matches']==[] and
   projection['whole_error_attribution_qualified'] is False and
   projection['task_cleanup_authority_created'] is False and projection['ok'] is False and
   projection['host_pid']==3268774 and projection['stderr_exactly_repeats_complete_message'] is True,
   'HISTORICAL_TIMEOUT_OBSERVATION_NOT_NATIVE_TASK_ATTRIBUTION')
  scope=hist.strict_json(get('scope'));attempt=hist.strict_json(get('attempted'))
  hist.qualify_scope(scope,attempt)
  raw=get('prelaunch_stacks');recorded=get('prelaunch_stdout')
  pr=hist.strict_json(get('prelaunch_result'));transport=hist.strict_json(get('prelaunch_transport'))
  need(raw==recorded,'COMPLETE_PRELAUNCH_STDOUT_BYTES')
  qualify_joined_command(pr,raw,False)
  command_sha=sha(json.dumps(hist.STACKS,separators=(',',':')).encode())
  need(transport.get('sequence')==6 and transport.get('epoch_sha256')==scope['epoch_sha256'] and
   transport.get('package')==PACKAGE and transport.get('uid')==10137 and transport.get('command_sha256')==command_sha and
   transport.get('returncode')==0 and transport.get('stdout_sha256')==sha(raw) and
   transport.get('stdout_bytes')==len(raw) and transport.get('stderr_bytes')==0 and
   transport.get('stderr_sha256')==sha(b'') and transport.get('outcome_unknown') is False and
   transport.get('automatic_retry') is False and transport.get('numeric_pid_target_used') is False,
   'EXACT_PRELAUNCH_HELD_TRANSPORT')
  need(hist.utc(pr['ended_utc'])<=hist.utc(attempt['time_utc'])<=hist.utc(intent['started_utc'])<=hist.utc(native_result['ended_utc']),
   'ORIGINAL_LAUNCH_TIME_ORDER')
  old_roots,old_tasks=parse(raw.decode('utf-8','strict'))
  need(hist.task_projection(raw,old_roots,old_tasks)==inputs['prelaunch'] and
   old_tasks=={875,876} and TASK not in old_tasks and TASK not in old_roots and
   not any(child['component'].split('/')[0]==PACKAGE for root in old_roots.values() for child in root['children']),
   'NO_IHG_PACKAGE_OR_TASK877_IN_COMPLETE_ORIGINAL_PRELAUNCH')
  need(r.access('launch_scope',False,optional=True) is None,'ORIGINAL_LAUNCH_SCOPE_MUST_REMAIN_ABSENT')
  samples=[]
  for number,row in enumerate(inputs['current_saved'],1):
   expected_path=FLOW/'steps/native-launch-state-read-02'/('current-stacks-%02d.txt'%number)
   command_path=FLOW/'steps/native-launch-state-read-02'/('command-%03d.result.json'%(number+4))
   need(row['sample']==number and row['path']==str(expected_path) and row['command']['path']==str(command_path),
    'EXACT_TWO_FIXED_SAVED_OBSERVATIONS')
   raw=read_exact(expected_path,{k:row[k] for k in ('bytes','sha256')},131072)
   cr=hist.strict_json(read_exact(command_path,{k:row['command'][k] for k in ('bytes','sha256')}))
   qualify_joined_command(cr,raw,False)
   need(hist.utc(native_result['ended_utc'])<=hist.utc(cr['ended_utc']),'SAVED_OBSERVATION_FOLLOWS_ORIGINAL_LAUNCH')
   roots,tasks=parse(raw.decode('utf-8','strict'))
   need(sha(canon(roots))==row['parsed_roots_sha256'] and tasks=={875,TASK} and set(roots)=={1,TASK} and
    exact_leaf(roots,TASK,PACKAGE) and roots[TASK]['children']==[{'id':TASK,'component':COMPONENT,'user':0}] and
    sha(canon(roots[1]))==inputs['preserved_root1_sha256'] and
    sha(canon(roots[TASK]))==inputs['current_root877_sha256'] and roots[1]==old_roots[1],
    'COMPLETE_SAVED_CURRENT_IHG877_AND_PRESERVED875')
   samples.append((roots,tasks))
  need(len(samples)==2 and samples[0]==samples[1],'EXACT_TWO_SAVED_TABLES_EQUAL')
  preserved_roots={k:v for k,v in samples[0][0].items() if k!=TASK}
  preserved_tasks=set(samples[0][1])-{TASK}
  need(preserved_tasks==set(inputs['preserved_current_tasks'])=={875} and
   set(preserved_roots)==set(inputs['preserved_current_root_ids'])=={1},'EXACT_CURRENT_PRESERVATION_BASELINE')
  need(r.opened==r.closed,'HISTORICAL_READER_FD_CLOSURE')
  safe={'fixed_historical_pins':observed,'actual_readers':inputs['evidence'],
   'native_intent_component':hist.COMPONENT,'canonical_public_component':COMPONENT,
   'component_not_present_in_original_prelaunch':True,'native_reported_task_id':None,
   'historical_launch_outcome':'unknown_retained','original_missing_Main_after_retained':True,
   'original_launch_scope_created':False,'original_task876_disappearance_attributed':False,
   'original_prelaunch_tasks':[875,876],'historical_current_tasks':[875,TASK],
   'preserved_current_tasks':[875],'entire_original_prelaunch_baseline_restored':False,
   'current_installed_native_source_version_verified':False,'whole_error_attribution_qualified':False,
   'reader_FDs_opened':r.opened,'reader_FDs_closed':r.closed,
   'current_saved_file_pins':inputs['current_saved']}
  return scope,preserved_roots,preserved_tasks,parse,exact_leaf,safe
 except BaseException as error:
  primary=error;raise
 finally:
  if r.opened!=r.closed:
   if primary is None:raise RuntimeError('HISTORICAL_READER_FD_CLOSURE')
   primary.add_note('HISTORICAL_READER_FD_CLOSURE')


def qualify_retirement02_saved_table(roots,tasks,prior_roots,prior_tasks,bound,exact_leaf):
 need(prior_tasks=={875} and set(prior_roots)=={1},'ORIGINAL_PRESERVED875_CHAIN_REQUIRED')
 need(bound['current_tasks']==[875,TASK,878] and bound['current_root_ids']==[1,TASK,878] and
  bound['preserved_current_tasks']==[875,878] and bound['preserved_current_root_ids']==[1,878] and
  tasks=={875,TASK,878} and set(roots)=={1,TASK,878},'EXACT_NEW_CURRENT_THREE_TASK_BASELINE')
 need(sha(canon(roots))==bound['complete_parsed_roots_sha256'] and
  set(bound['root_record_sha256'])=={'1',str(TASK),'878'} and
  all(sha(canon(root))==bound['root_record_sha256'][str(rid)] for rid,root in roots.items()),
  'EXACT_NEW_CURRENT_COMPLETE_ROOT_HASHES')
 need(roots[1]==prior_roots[1] and exact_leaf(roots,TASK,PACKAGE) and
  roots[TASK]['children']==[{'id':TASK,'component':COMPONENT,'user':0}] and
  bound['target_component']==COMPONENT,'SAME_IHG877_AND_ORIGINAL875_COMPLETE_RECORDS')
 other=roots[878];need(other['display']==0 and other['user']==0 and other['freeform'] is True and
  len(other['children'])==1 and other['children'][0]['id']==878 and other['children'][0]['user']==0,
  'EXACT_PRESERVED878_ROOT_AND_LEAF')
 component=other['children'][0]['component'];raw=component.encode('utf-8','strict')
 need(component.split('/')[0]!=PACKAGE and bound['foreign878_component']==
  {'bytes':len(raw),'sha256':sha(raw),'package_is_IHG':False},'EXACT_FOREIGN878_HASH_ONLY_BINDING')
 return {key:value for key,value in roots.items() if key!=TASK},set(tasks)-{TASK}

def qualify_retirement02_fresh_table(roots,tasks,saved_roots,saved_tasks,preserved_roots,preserved_tasks,exact_leaf):
 gate=qualify_task_set(roots,tasks,preserved_roots,preserved_tasks,TASK,exact_leaf)
 if gate['status']=='exact_live_leaf':
  need(roots==saved_roots and tasks==saved_tasks,'FRESH_COMPLETE_TABLE_DIFFERS_FROM_CURRENT_BASELINE02')
 else:
  need(gate=={'status':'already_absent','removal_allowed':False} and
   roots==preserved_roots and tasks==preserved_tasks,'ABSENT877_REQUIRES_ALL_CURRENT_OTHER_CONTENT')
 return gate

def verify_retirement02_baseline(hist,inputs,prior_roots,prior_tasks,parse,exact_leaf):
 bound=inputs['current_retirement02_baseline'];previous=bound['prior_failed_run']
 need(bound['schema']=='pocket4-independent-current-IHG877-retirement02-baseline-v1' and
  previous['source_sha256']=='c2f3d2e849d3d2dbabd58d5c6ebf35ad7cb6c729a153a94bf415f780fb94fbfc' and
  previous['step_name']=='current-ihg877-independent-retirement-01' and previous['ok'] is False and
  previous['first_error']=={'exception_type':'RuntimeError','fixed_code':'OTHER_TASK_SET_CHANGED',
   'message_sha256':'822aca1d3693d9ce997c9600640cb0abbb958113cf18c14feb0c2bd957073bc3',
   'phase':'current_complete_table_1','raw_message_exported':False} and
  all(previous[key] is False for key in ('remove_requested','remove_acknowledged','removal_action_attempted',
   'retirement_outcome_unknown')) and
  previous['actual_command_count']==9 and previous['controls_passed']==38 and
  previous['helper_UiAutomation_calls']==previous['native_launches']==0 and
  previous['historical_launch_outcome']=='unknown_retained' and
  previous['current_Main_window_complete'] is True and
  all(previous[key]==MAIN_BEFORE_FIXED for key in ('Main_before_lock','Main_after_locks','Main_after')) and
  previous['target_helper_before_after_unchanged'] is True and previous['target_FD_closed']==1 and
  all(previous[key] is True for key in ('held_binding_released','flow_lock_released','global_action_lock_released')),
  'EXACT_PRIOR_READ_ONLY_FAILED01_WITHOUT_REMOVE')
 need(bound['actual_failed_retirement']=={'tree':'9398613a97fc015d4d202c50f1ffffcfa4213de6',
  'blob':'eef5723a89f6e55c3cb6dec46d593e4b18d38178','bytes':24051,
  'sha256':'dd040d4a5ac8050a2fd3d854e0dec74be386c048f33b68d0e4b200aaa4a79e9a'} and
  bound['actual_saved_projection']=={'tree':'7e292c099ab91f6ee0baf677edaeeedae20f761f',
  'blob':'690f9bf079567e23b9ac44194d5918fc92a5844c','bytes':6956,
  'sha256':'c0a2ba798ead0f887b44f86a0e124e38762039d4b2bd9d309ad0ec648056ff70'} and
  bound['saved_file_count']==2 and bound['independent_prior_Android_samples']==1 and
  bound['foreign878_source_attributed'] is False and
  bound['original_launch_outcome_unknown_retained'] is True and
  bound['previous_retirement01_failure_retained'] is True and
  bound['previous_retirement01_replayed'] is False and
  bound['current_Main_requalified_by_saved_reader'] is False and
  bound['cleanup_authority_created_by_saved_reader'] is False,'EXACT_ACTUAL_CURRENT_BASELINE02_PROVENANCE')
 old_step=FLOW/'steps/current-ihg877-independent-retirement-01'
 command=bound['command005']
 need(command['path']==str(old_step/'command-005.result.json') and
  {'bytes':command['bytes'],'sha256':command['sha256']}==
   {'bytes':443,'sha256':'f887e2f9da435418a3c6da526efb258015a734c8b901ed29b62f0a7652c40879'},
  'EXACT_PRIOR_COMMAND005_PIN')
 record=hist.strict_json(read_exact(Path(command['path']),{key:command[key] for key in ('bytes','sha256')}))
 need(record==command['record'],'ORIGINAL_FAILED01_COMMAND005_RECORD_UNCHANGED')
 old_last=inputs['current_saved'][1]['command']
 older=hist.strict_json(read_exact(Path(old_last['path']),{key:old_last[key] for key in ('bytes','sha256')}))
 need(hist.utc(older['ended_utc'])<=hist.utc(record['ended_utc']),'NEW_CURRENT_BASELINE_OBSERVATION_ORDER')
 expected_files=[old_step/'command-005.stdout',old_step/'before-stacks-01.txt']
 need(type(bound['saved_files']) is list and len(bound['saved_files'])==2,'EXACT_TWO_SAVED_COPIES_REQUIRED')
 observed=[]
 for item,path in zip(bound['saved_files'],expected_files):
  need(item['path']==str(path) and {'bytes':item['bytes'],'sha256':item['sha256']}==
   {'bytes':1963,'sha256':'bf84e8d77523a712a7b4dc5712dea5ab7e65d7c0a6c3b285eed2b30baec18b8b'},
   'EXACT_NEW_CURRENT_SAVED_FILE_ALLOWLIST')
  raw=read_exact(path,{key:item[key] for key in ('bytes','sha256')},131072)
  qualify_joined_command(record,raw,False)
  roots,tasks=parse(raw.decode('utf-8','strict'))
  kept_roots,kept_tasks=qualify_retirement02_saved_table(roots,tasks,prior_roots,prior_tasks,bound,exact_leaf)
  need(sha(canon(roots[1]))==inputs['preserved_root1_sha256'] and
   sha(canon(roots[TASK]))==inputs['current_root877_sha256'],'PRIOR875_AND877_FULL_CONTENT_UNCHANGED')
  observed.append((raw,roots,tasks,kept_roots,kept_tasks))
 need(observed[0]==observed[1] and
  not os.path.lexists(old_step/'remove-attempted.json') and
  not os.path.lexists(old_step/'independent-current-retirement.json'),
  'FAILED01_TWO_COMPLETE_COPIES_NO_OLD_REMOVE_OR_SUCCESS')
 _,roots,tasks,kept_roots,kept_tasks=observed[0]
 safe={'schema':bound['schema'],'actual_failed_retirement':bound['actual_failed_retirement'],
  'actual_saved_projection':bound['actual_saved_projection'],'prior_failed_step':previous['step_name'],
  'prior_failure':'OTHER_TASK_SET_CHANGED','prior_remove_attempted':False,'prior_outcome_unknown':False,
  'one_prior_Android_sample_in_two_files':True,'saved_files':bound['saved_files'],
  'command005':{'path':command['path'],'bytes':command['bytes'],'sha256':command['sha256']},
  'complete_current_roots_sha256':sha(canon(roots)),
  'complete_preserved_roots_sha256':sha(canon(kept_roots)),
  'current_tasks':sorted(tasks),'preserved_tasks':sorted(kept_tasks),
  'root_record_sha256':bound['root_record_sha256'],'foreign878_source_attributed':False,
  'foreign_component_names_exported':False,'historical_launch_outcome':'unknown_retained',
  'fresh_complete_pair_still_required':True}
 return roots,tasks,kept_roots,kept_tasks,safe

def retirement02_gate_controls(exact_leaf):
 cases=[]
 def passed(name,value):need(value,'RETIREMENT02_CONTROL_'+name.upper());cases.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name,True);return
  raise RuntimeError('RETIREMENT02_NEGATIVE_ACCEPTED_'+name.upper())
 def clone(value):return json.loads(json.dumps(value))
 prior={1:{'display':0,'user':0,'freeform':False,'children':[{'id':875,'user':0,'component':'fixture.system/Fixture'}]}}
 roots={**prior,TASK:{'display':0,'user':0,'freeform':True,
  'children':[{'id':TASK,'user':0,'component':COMPONENT}]},
  878:{'display':0,'user':0,'freeform':True,'children':[{'id':878,'user':0,'component':'fixture.other/Activity'}]}}
 bound={'current_tasks':[875,TASK,878],'current_root_ids':[1,TASK,878],
  'preserved_current_tasks':[875,878],'preserved_current_root_ids':[1,878],
  'complete_parsed_roots_sha256':sha(canon(roots)),
  'root_record_sha256':{str(key):sha(canon(value)) for key,value in roots.items()},
  'target_component':COMPONENT,
  'foreign878_component':{'bytes':len(b'fixture.other/Activity'),'sha256':sha(b'fixture.other/Activity'),'package_is_IHG':False}}
 kept,ids=qualify_retirement02_saved_table(roots,{875,TASK,878},prior,{875},bound,exact_leaf)
 passed('saved-three-task-current-baseline-preserves875-and878',set(kept)=={1,878} and ids=={875,878})
 rejected('saved-current-complete-hash-drift-rejected',lambda:qualify_retirement02_saved_table(
  roots,{875,TASK,878},prior,{875},{**bound,'complete_parsed_roots_sha256':'0'*64},exact_leaf))
 def fresh(value,tasks):
  return qualify_retirement02_fresh_table(value,tasks,roots,{875,TASK,878},kept,ids,exact_leaf)
 passed('fresh-complete-three-task-table-required',
  fresh(roots,{875,TASK,878})=={'status':'exact_live_leaf','removal_allowed':True})
 passed('already-absent877-preserves-both-other-tasks-without-action',
  fresh(kept,{875,878})=={'status':'already_absent','removal_allowed':False})
 rejected('missing-preserved878-old-two-task-baseline-rejected',
  lambda:fresh({key:value for key,value in roots.items() if key!=878},{875,TASK}))
 changed={key:clone(value) for key,value in roots.items()}
 changed[878]['children'][0]['component']='fixture.other/Changed'
 rejected('changed-preserved878-complete-content-rejected',lambda:fresh(changed,{875,TASK,878}))
 changed875={key:clone(value) for key,value in roots.items()}
 changed875[1]['children'][0]['component']='fixture.system/Changed'
 rejected('changed-preserved875-complete-content-rejected',lambda:fresh(changed875,{875,TASK,878}))
 rejected('additional879-task-rejected',lambda:fresh({**roots,879:clone(roots[878])},{875,TASK,878,879}))
 need(len(cases)==8,'EXACT_EIGHT_CURRENT_BASELINE02_CONTROLS')
 return cases


def new_retirement_scope(source_sha):
 return {'schema':'pocket4-independent-current-IHG-task-retirement-scope-v1',
  'task':TASK,'component':COMPONENT,'package':PACKAGE,'uid':10137,'user':0,
  'epoch_sha256':'7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c',
  'baseline_sha256':'633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364',
  'qualification_sha256':'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e',
  'source_sha256':source_sha,'prelaunch_absent':True,'cleanup_allowed':True,
  'independent_current_scope':True,'original_launch_outcome':'unknown_retained',
  'original_launch_scope_created':False,'authorizes_original_action_replay':False,
  'native_reported_task_id':None}

def independent_scope_controls(owned,task,qa,resolve,plans,exact_leaf,source_sha):
 cases=[];bound=new_retirement_scope(source_sha)
 def passed(name):cases.append({'name':name,'passed':True})
 def rejected(name,call):
  try:call()
  except RuntimeError:passed(name);return
  raise RuntimeError('INDEPENDENT_SCOPE_CONTROL_ACCEPTED')
 need(owned.validate_retirement_scope(bound,source_sha),'NEW_SCOPE_POSITIVE');passed('exact-new-current-scope-positive')
 rejected('source-pin-drift-rejected',lambda:owned.validate_retirement_scope(bound,'0'*64))
 rejected('native-task-id-claim-rejected',lambda:owned.validate_retirement_scope({**bound,'native_reported_task_id':TASK},source_sha))
 rejected('wrong-public-component-rejected',lambda:owned.validate_retirement_scope({**bound,'component':PACKAGE+'/Other'},source_sha))
 cls=owned.make_flow_type(task,bound,source_sha)
 def fixture():
  f=object.__new__(cls);calls=[]
  f.retirement_authority=None;f.retirement_counts={};f.retirement_remove_attempted=False
  f.command_index=0;f.action_attempted=False;f.launch_claimed=False;f.poisoned=False;f.closed=False
  f._private_backend_transport=False;f._android_mutation=False
  f.guard=lambda attempted=False:None # Explicit Main/held IO seam, not runtime qualification.
  f.tasks=types.SimpleNamespace(exact_leaf=exact_leaf)
  f.policy=task.Policy('cleanup',qa,resolve,plans,Path('/synthetic-current-retirement'),lambda *a:None,f.selected_task)
  def transport(argv,timeout):
   calls.append((list(argv),timeout,f._android_mutation));f.command_index+=1
   if f._android_mutation:f.action_attempted=True
   return b'fixture'
  f.transport=transport
  return f,calls
 f,calls=fixture()
 rejected('unarmed-remove-before-transport-rejected',
  lambda:f.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True))
 need(calls==[] and f.command_index==0,'UNARMED_REMOVE_FORWARDED')
 f,calls=fixture()
 base={1:{'display':0,'user':0,'freeform':False,'children':[{'id':875,'user':0,'component':'fixture.system/Fixture'}]}}
 roots={**base,TASK:{'display':0,'user':0,'freeform':True,'children':[{'id':TASK,'user':0,'component':COMPONENT}]}}
 for argv,timeout in ((task.LIST,15),(task.PATHS,15),(task.OWN_UID,8),(task.OWN_PATH,8),(task.STACKS,20),(task.STACKS,20)):
  f.android(list(argv),timeout)
 f.arm_after_exact_pair(roots,{875,TASK},roots,{875,TASK},base,{875})
 f.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True)
 need(f.command_index==7 and f.action_attempted is True and f.policy.remove_attempted is True and
  f.policy.counts=={'target_uid':1,'target_path':1,'helper_uid':1,'helper_path':1,'stacks':2} and
  f.retirement_counts=={**f.policy.counts,'remove':1} and
  calls[-1]==(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,True),
  'REAL_ORIGINAL_POLICY_AND_FLOW_ANDROID_DELEGATION')
 passed('six-reads-new-scope-original-Policy-Flow-single-remove-route')
 rejected('second-remove-never-forwarded',lambda:f.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True))
 need(len(calls)==7,'SECOND_REMOVE_FORWARDED')
 f,calls=fixture()
 rejected('foreign-remove-never-forwarded',lambda:f.android(['/system/bin/cmd','activity','stack','remove','876'],20,mutation=True))
 need(calls==[],'FOREIGN_REMOVE_FORWARDED')
 f,calls=fixture();f.android(list(task.STACKS),0.125)
 need(calls==[(list(task.STACKS),0.125,False)] and f.policy.counts=={'stacks':1},
  'ORIGINAL_COMPLETION_FRACTIONAL_REMAINING_BUDGET')
 passed('fractional-original-completion-timeout-delegates')
 need(len(cases)==9,'EXACT_NINE_INDEPENDENT_SCOPE_CONTROLS')
 return cases

def open_context_route_controls(task,q,plans,scope,source_sha):
 """Execute the real new open_context body; all OS/source/held I/O is explicitly synthetic."""
 cases=[]
 def run_fixture(mode):
  module=types.ModuleType('synthetic_IO_only_owned_retirement_context')
  exec(compile(OWNED_CONTEXT_SOURCE,'<exact-owned-context-with-explicit-IO-seams>','exec'),module.__dict__)
  events=[];written=[];targets=[]
  class P:
   def __init__(self,value):self.value=value
   def __truediv__(self,tail):return P(self.value+'/'+str(tail))
   def __str__(self):return self.value
   def is_dir(self):return True
   def is_relative_to(self,root):return self.value.startswith(str(root)+'/')
   def lstat(self):return types.SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
  root=P('/synthetic/flow');step=root/'steps/current-retirement'
  init={'host_pid':1};activation={'framework_epoch':{'binding':{'processes':{'init':init}}},'status':{'host_pid':2}}
  expected_scope=json.loads(json.dumps(scope));epoch=object()
  class Target:
   def __init__(self,actual,path,digest):
    need(actual==init,'FIXTURE_TARGET_IDENTITY');self.record=dict(actual);self.closed=False;targets.append(self)
   def verify(self):need(not self.closed,'FIXTURE_CLOSED_TARGET')
   def close(self):self.closed=True;events.append('held.close')
  def proc_open(path,flags):
   need(path=='/proc/1','FIXTURE_FIXED_PROC');events.append('proc.open');return 7
  def proc_close(fd):
   need(fd==7,'FIXTURE_FD');events.append('proc.close')
  module.os=types.SimpleNamespace(open=proc_open,close=proc_close,O_RDONLY=os.O_RDONLY,
   O_DIRECTORY=os.O_DIRECTORY,O_NOFOLLOW=os.O_NOFOLLOW,O_CLOEXEC=os.O_CLOEXEC)
  recorder=types.SimpleNamespace(APP='/synthetic/app.py',APP_SHA='1'*64,
   task_functions=lambda path:types.SimpleNamespace(exact_leaf=lambda *a:True))
  held=types.SimpleNamespace(proc_identity_at=lambda fd,pid,deadline:dict(init),HeldTarget=Target)
  def classpaths(held_arg,target_arg,framework,epoch_arg,guard):
   guard();events.append('classpath');return {'CLASSPATH':'synthetic'},{'synthetic':True}
  binding=types.SimpleNamespace(same_epoch_identity=lambda left,right:left==right,main_classpaths=classpaths)
  def load(name,label):
   need(name in ('recorder.py','references/held_runtime_r5.py','main_binding.py'),'FIXTURE_EXACT_MODULE')
   return {'recorder.py':recorder,'references/held_runtime_r5.py':held,'main_binding.py':binding}[name]
  contract=types.SimpleNamespace(sha256=task.CURRENT_HOST_MANIFEST,verify=lambda:events.append('contract.verify'),load=load)
  source=types.SimpleNamespace(SourceContract=lambda path,pin:contract,HELPER_PATH=P('/synthetic/helper'),HELPER_BYTES=1,
   HELPER_SHA='2'*64,verify_shared_helper=lambda:{'whole_process_tree_cleanup_qualified':False})
  def module_read(path,*args,**kwargs):
   value=str(path)
   if value.endswith('/scope.json'):return canon(expected_scope)
   if value.endswith('/baseline.json') or value=='/synthetic/baseline':return b'B'
   if value.endswith('/baseline-qualification.json') or value=='/synthetic/qualification':return b'Q'
   return b'x'
  def load_module(path,pin,label):
   return source if str(path).endswith('/source_contract.py') else types.SimpleNamespace()
  util=types.SimpleNamespace(module=load_module,read=module_read,verify_source=lambda sha:None,HERE=P('/synthetic/install-source'))
  def main_guard(baseline,epoch_arg):
   need(baseline is activation and epoch_arg is epoch,'FIXTURE_MAIN_ARGUMENTS')
   events.append('Main.guard');return dict(MAIN_BEFORE_FIXED)
  def write_new(path,value):written.append((str(path),value))
  ref=types.SimpleNamespace(current_baseline=lambda:activation,EPOCH_SOURCE='/synthetic/epoch.py',EPOCH_SOURCE_SHA='3'*64,
   module=lambda *args:epoch,read=module_read,main_guard=main_guard,write_new=write_new,
   BASELINE='/synthetic/baseline',BASELINE_SHA=task.CURRENT_BASELINE_SHA,
   QUALIFICATION='/synthetic/qualification',QUALIFICATION_SHA=task.CURRENT_QUALIFICATION_SHA)
  def discover(*args):
   events.append('current.discovery')
   return (99 if mode=='wrong_discovery_init' else 1),{'CLASSPATH':'synthetic'},{'host_pid':2}
  context=types.SimpleNamespace(INSTALLED_SHARED=P('/synthetic/shared'),CONTRACT_SHA='4'*64,
   SHARED_MANIFEST=task.CURRENT_HOST_MANIFEST,baseline_scope=lambda *args:{'package':PACKAGE,'uid':10137},
   verify_target_data=lambda *args:None,current_discovery=discover)
  transport=types.SimpleNamespace(FRAMEWORK_EPOCH_SHA256=task.CURRENT_EPOCH,
   environment_values=lambda value:dict(value),BoundArun=lambda **kwargs:object())
  def verify_runtime(value):
   need(value==SOURCE_MANIFEST,'FIXTURE_SOURCE_ARGUMENT')
   if mode=='reject_source':raise RuntimeError('SYNTHETIC_SOURCE_REJECTED')
   events.append('source.verify')
  flow_type=module.make_flow_type(task,new_retirement_scope(source_sha),source_sha)
  result={}
  try:
   flow,actual_recorder,guard=module.open_independent_context(task,flow_type,ref,util,context,SOURCE_MANIFEST,verify_runtime,
    root,step,transport,result,time.monotonic()+30,'cleanup',q.qa,plans,q.resolver.RESOLVE,expected_scope,
    install_source_manifest=q.resolver.INSTALL_SOURCE_SHA)
  except RuntimeError as error:
   if mode=='reject_source':
    need(str(error)=='SYNTHETIC_SOURCE_REJECTED' and not targets and not written and 'proc.open' not in events,
     'SOURCE_FAILURE_BEFORE_HELD_IO')
   elif mode=='wrong_discovery_init':
    need(str(error)=='FIXED_MAIN_DISCOVERY_CHANGED' and len(targets)==1 and targets[0].closed and not written and
     events.count('proc.open')==events.count('proc.close')==events.count('held.close')==1,
     'WRONG_DISCOVERY_INIT_CLOSES_OWNED_HELD_TARGET')
   else:raise
   return
  need(mode=='positive' and actual_recorder is recorder and isinstance(flow,flow_type) and
   len(written)==1 and written[0][0]==str(step/'held-main-binding.json') and
   written[0][1]['target_package']==PACKAGE and written[0][1]['target_uid']==10137 and
   written[0][1]['amazon_task_runtime_source_manifest']==SOURCE_MANIFEST and
   written[0][1]['Bili_Flow_instantiated'] is False and
   flow.scope==expected_scope and flow.policy.phase=='cleanup' and
   flow.retirement_authority is None and
   events.count('proc.open')==events.count('proc.close')==1 and not targets[0].closed,
   'REAL_OPEN_CONTEXT_REACHES_TYPED_HELD_BINDING_WITH_UID')
  flow.close();need(targets[0].closed and events.count('held.close')==1,'RETURNED_FLOW_CLOSES_HELD_TARGET')
 for mode,name in (('positive','real-open-context-reaches-held-binding-UID-and-original-Flow'),
  ('reject_source','real-open-context-source-rejection-before-held-IO'),
  ('wrong_discovery_init','real-open-context-wrong-discovery-init-closes-held-target')):
  run_fixture(mode);cases.append({'name':name,'passed':True})
 need(len(cases)==3,'EXACT_THREE_OPEN_CONTEXT_ROUTE_CONTROLS')
 return cases

def run(source_sha256):
 need(os.getuid()==os.geteuid()==0,'ROOT_CURRENT_RETIREMENT_REQUIRED')
 os.umask(0o077)
 result={'schema':'pocket4-independent-current-IHG877-retirement-v2','ok':False,
  'source_sha256':source_sha256,'step_name':STEP_NAME,'task':TASK,'errors':[],'command_records':[],
  'historical_launch_outcome':'unknown_retained','original_launch_scope_created':False,
  'native_reported_task_id':None,'historical_Main_after_filled':False,
  'original_task876_disappearance_attributed':False,'entire_original_prelaunch_baseline_restored':False,
  'native_registration_replayed':False,'Composer_control_remove_sent':False,'native_launches':0,
  'maximum_Android_task_remove_commands':1,'remove_requested':False,'remove_acknowledged':False,
  'removal_action_attempted':False,'retirement_outcome_unknown':False,
  'before_tables':[],'completion_observations':[],'independent_after_attempted':False,
  'independent_after_completed':False,'global_action_lock_released':False,'flow_lock_released':False,
  'held_binding_released':False,'whole_process_tree_cleanup_qualified':False,
  'helper_UiAutomation_calls':0,'old_helper_nonce_values_consumed':False,
  'business_success_verified':False,'whole_app_production_ready':False}
 flow=recorder=artifacts=session=action_lock=flow_lock=resources=q=entry=u=ref=guard=None
 preserved_roots=preserved_tasks=None;current_baseline_roots=current_baseline_tasks=None
 step_created=False;phase='fixed_historical_chain';began=time.monotonic()
 def remember(where,error):result['errors'].append({'phase':where,**safe_error(error)})
 def record_command(number):
  path=str(STEP/('command-%03d.result.json'%number))
  existing=next((x for x in result['command_records'] if x['path']==path),None)
  if existing is None:
   existing=owned_command_record(number);result['command_records'].append(existing)
  return existing['record']
 def preserve(roots,tasks):
  need(set(tasks)-{TASK}==set(preserved_tasks),'OTHER_TASK_SET_CHANGED')
  need(set(roots)-{TASK}==set(preserved_roots),'OTHER_ROOT_SET_CHANGED')
  need(all(roots.get(k)==v for k,v in preserved_roots.items()),'PREEXISTING_ROOT_CONTENT_CHANGED')
 def observed(raw,roots,tasks):
  return {'raw_stack_pin':pin(raw),'tasks':summary(roots,tasks),
   'complete_parsed_roots_sha256':sha(canon(roots)),
   'other_complete_root_content_sha256':sha(canon({k:v for k,v in roots.items() if k!=TASK})),
   'target_absent':TASK not in roots and TASK not in tasks,
   'foreign_component_names_exported':False}
 def current_table(label,timeout=20):
  raw=flow.android(task.STACKS,timeout)
  qualify_joined_command(record_command(flow.command_index),raw,False)
  roots,tasks=flow.tasks.parse_stacks(raw.decode('utf-8','strict'))
  need(len(roots)<=256 and len(tasks)<=512,'CURRENT_COMPLETE_TASK_TABLE_BOUND')
  ref.write_new(STEP/(label+'.txt'),raw)
  return raw,roots,tasks
 try:
  need(pin(HISTORICAL_PARSER_SOURCE.encode())==HISTORICAL_PARSER_PIN,'EXACT_EXECUTED_NATIVE007_SOURCE')
  hist=types.ModuleType('fixed_historical_IHG_native007');hist.__file__='<fixed-historical-IHG-native007>'
  hist.SOURCE_SHA256=HISTORICAL_PARSER_PIN['sha256']
  exec(compile(HISTORICAL_PARSER_SOURCE,hist.__file__,'exec'),hist.__dict__)
  scope,preserved_roots,preserved_tasks,parse,exact_leaf,historical=verify_historical(hist,INPUTS,read_exact,qualify_joined_command)
  result['historical_chain']=historical
  current_baseline_roots,current_baseline_tasks,preserved_roots,preserved_tasks,current_basis=verify_retirement02_baseline(
   hist,INPUTS,preserved_roots,preserved_tasks,parse,exact_leaf)
  result['independent_current_baseline02']=current_basis
  need(not os.path.lexists(STEP) and not os.path.lexists(FLOW/'launch-scope.json'),'NO_CURRENT_RETIREMENT_OR_ORIGINAL_SCOPE_REPLAY')
  entry_raw=read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
  entry=types.ModuleType('fixed_ihg_current_retirement_entry');entry.__file__=str(SOURCE/'owned_inspect.py')
  exec(compile(entry_raw,entry.__file__,'exec'),entry.__dict__)
  need(entry.HERE==SOURCE and entry.FLOW==FLOW and entry.PACKAGE==PACKAGE and entry.HELPER_UID==10158,
   'EXACT_CURRENT_IHG_ENTRY')
  q=entry.qualified(SOURCE_MANIFEST);u,ref=q.util,q.ref
  task=entry.load(SOURCE/'ihg_task_context.py',q.manifest['files']['ihg_task_context.py']['sha256'],'fixed_IHG_original_task_context')
  context=u.module(q.resolver.INSTALL_SOURCE/'ihg_context.py',q.resolver.CONTEXT_SHA,'fixed_IHG_install_artifact_context')
  transport=u.module(q.resolver.INSTALL_SOURCE/'ihg_transport.py',q.resolver.TRANSPORT_SHA,'fixed_IHG_held_transport')
  shared=u.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'fixed_current_source_contract')
  contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
  recorder=contract.load('recorder.py','fixed_current_original_command')
  activation=ref.current_baseline()
  epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'fixed_current_epoch')
  guard=lambda:ref.main_guard(activation,epoch)
  need(pin(OWNED_CONTEXT_SOURCE.encode())==OWNED_CONTEXT_PIN,'EXACT_OWNED_RETIREMENT_CONTEXT')
  owned=types.ModuleType('owned_IHG_current_retirement_context');owned.__file__='<verified-owned-IHG-retirement-context>'
  exec(compile(OWNED_CONTEXT_SOURCE,owned.__file__,'exec'),owned.__dict__)
  bound_scope=new_retirement_scope(source_sha256)
  flow_type=owned.make_flow_type(task,bound_scope,source_sha256)
  plans=current_read_plans(entry)
  phase='admission';resources=u.prepare_owned_limits();result['owned_before']=resources
  result['Main_before_lock']=guard()
  need(result['Main_before_lock']==MAIN_BEFORE_FIXED,'FRESH_CURRENT_MAIN_BASELINE_DIFFERS')
  result['controls']=task_set_controls(exact_leaf)+command_gate_controls()+current_main_window_controls()+independent_scope_controls(
   owned,task,q.qa,q.resolver.RESOLVE,plans,exact_leaf,source_sha256)+open_context_route_controls(task,q,plans,scope,source_sha256)+retirement02_gate_controls(exact_leaf)
  need(len(result['controls'])==46 and len({x['name'] for x in result['controls']})==46,'EXACT_FORTY_SIX_CONTROLS')
  result['flow_lock_admission']={};flow_lock=u.acquire_action_lock(FLOW/'flow.lock',result['flow_lock_admission'])
  result['global_lock_admission']={};action_lock=u.acquire_action_lock(recorder.ACTION_LOCK,result['global_lock_admission'])
  result['Main_after_locks']=guard()
  need(not os.path.lexists(STEP) and not os.path.lexists(FLOW/'launch-scope.json'),'NO_RETIREMENT_STEP_OR_OLD_SUCCESS_SCOPE')
  STEP.mkdir(mode=0o700);step_created=True
  ref.write_new(STEP/'intent.json',{'schema':'pocket4-independent-current-retirement-intent-v1',
   'source_sha256':source_sha256,'task':TASK,'component':COMPONENT,'historical_launch_outcome':'unknown_retained',
   'native_reported_task_id':None,'current_preserved_tasks':[875,878],'original_task876_disappearance_attributed':False,
   'independent_current_baseline02':current_basis,
   'maximum_remove_commands':1,'maximum_completion_reads':30,'maximum_total_commands':42,
   'native_launches':0,'helper_instrumentation_calls':0,'automatic_retry':False})
  def verify_runtime(value):
   entry.verify_source(value);u.verify_source(q.resolver.INSTALL_SOURCE_SHA)
   entry.read(entry.RESOLVER_SOURCE,32768,entry.RESOLVER_SHA,entry.RESOLVER_BYTES)
   read_exact(SOURCE/'owned_inspect.py',ENTRY_PIN)
   for item in INPUTS['fixed_historical_files'].values():
    read_exact(Path(item['path']),{k:item[k] for k in ('bytes','sha256')},131072)
   for item in INPUTS['current_saved']:
    read_exact(Path(item['path']),{k:item[k] for k in ('bytes','sha256')},131072)
    read_exact(Path(item['command']['path']),{k:item['command'][k] for k in ('bytes','sha256')})
   current_inputs=INPUTS['current_retirement02_baseline']
   for item in current_inputs['saved_files']+[current_inputs['command005']]:
    read_exact(Path(item['path']),{key:item[key] for key in ('bytes','sha256')},131072)
   need(not os.path.lexists(FLOW/'launch-scope.json'),'ORIGINAL_LAUNCH_SCOPE_MUST_REMAIN_ABSENT')
  phase='held_current_IHG_context'
  flow,recorder,phase_guard=owned.open_independent_context(task,flow_type,ref,u,context,SOURCE_MANIFEST,verify_runtime,
   FLOW,STEP,transport,result,began+175,'cleanup',q.qa,plans,q.resolver.RESOLVE,scope,
   install_source_manifest=q.resolver.INSTALL_SOURCE_SHA)
  need(flow.scope==scope and flow.tasks.parse_stacks is not None,'CURRENT_TYPED_CONTEXT_REQUIRED')
  reference=json.loads(u.read(q.resolver.INSTALL_SOURCE/'target-artifact-reference.json',
   expected=q.install_manifest['files']['target-artifact-reference.json']['sha256']))
  reader=u.module(q.resolver.INSTALL_SOURCE/'references/read_ihg.py',u.READER_SHA,'current_IHG_artifact_parser')
  artifacts=context.ArtifactSet(flow,reference,reader)
  phase='current_target_before';result['target_before']=artifacts.before()
  session=q.adapter.Session(flow,recorder,q.qa,q.proof,entry.HELPER_UID)
  phase='current_helper_before';result['helper_before']=session.installed()
  need(result['helper_before']==q.installed and flow.command_index==4,'EXACT_CURRENT_INSTALLED_HELPER')
  fresh=[]
  for number in (1,2):
   phase='current_complete_table_'+str(number)
   raw,roots,tasks=current_table('before-stacks-%02d'%number)
   need(flow.command_index==4+number and flow.action_attempted is False and not flow.launch_claimed,'ONLY_SIX_PRE_RETIREMENT_READS')
   gate=qualify_retirement02_fresh_table(roots,tasks,current_baseline_roots,current_baseline_tasks,
    preserved_roots,preserved_tasks,flow.tasks.exact_leaf)
   fresh.append((roots,tasks));result['before_tables'].append({**observed(raw,roots,tasks),'qualification':gate})
   flow.guard()
  need(fresh[0]==fresh[1] and result['before_tables'][0]['qualification']==result['before_tables'][1]['qualification'],
   'FRESH_COMPLETE_TABLES_CHANGED_NO_RETRY')
  result['before_tables_qualified']=True
  if gate['status']=='already_absent':
   result['already_absent_without_removal']=True
  else:
   phase='arm_new_current_scope'
   flow.arm_after_exact_pair(fresh[0][0],fresh[0][1],fresh[1][0],fresh[1][1],preserved_roots,preserved_tasks)
   ref.write_new(STEP/'new-current-retirement-scope.json',bound_scope);result['new_current_retirement_scope_armed']=True
   flow.guard()
   ref.write_new(MARKER,{'schema':'pocket4-independent-current-retirement-attempt-v1','scope':bound_scope,
    'source_sha256':source_sha256,'time_utc':recorder.now(),'automatic_retry':False,
    'original_launch_scope_created':False})
   phase='one_exact_Android_remove877';result['remove_requested']=True
   removed=flow.android(['/system/bin/cmd','activity','stack','remove',str(TASK)],20,mutation=True)
   need(flow.command_index==7,'EXACT_SINGLE_REMOVE_INDEX')
   qualify_joined_command(record_command(7),removed,True);result['remove_acknowledged']=True
   completion_reads=0
   def completion_stacks(timeout):
    nonlocal completion_reads
    need(completion_reads<30,'COMPLETION_CAP_PRESERVES_INDEPENDENT_AFTER_SLOT')
    completion_reads+=1
    raw=flow.android(task.STACKS,timeout)
    need(flow.command_index<=37,'THIRTY_COMPLETION_READS_BOUND')
    qualify_joined_command(record_command(flow.command_index),raw,False)
    return raw.decode('utf-8','strict')
   def completion_record(value):
    index=len(result['completion_observations'])+1
    ref.write_new(STEP/('completion-private-%02d.json'%index),value)
    need(type(value) is dict and type(value.get('raw_stacks')) is str,'COMPLETE_COMPLETION_TABLE')
    roots,tasks=flow.tasks.parse_stacks(value['raw_stacks']);preserve(roots,tasks)
    if TASK in tasks:
     need(roots.get(TASK,{}).get('children')==[{'id':TASK,'component':COMPONENT,'user':0}],
      'CURRENT_TARGET_CHANGED_DURING_RETIREMENT')
    result['completion_observations'].append({'observation':index,**observed(value['raw_stacks'].encode(),roots,tasks)})
   phase='original_bounded_removal_completion'
   result['normal_completion']=flow.tasks.wait_for_removal(completion_stacks,TASK,PACKAGE,fresh[-1][1],completion_record)
   result['normal_removal_verified']=True
 except BaseException as error:remember(phase,error)
 finally:
  if flow is not None and result.get('before_tables_qualified') is True:
   result['independent_after_attempted']=True
   try:
    raw,roots,tasks=current_table('independent-after-stacks')
    preserve(roots,tasks);result['independent_after']=observed(raw,roots,tasks)
    need(TASK not in tasks and TASK not in roots and roots==preserved_roots and tasks==preserved_tasks,
     'EXACT_CURRENT_TARGET_ABSENT_AND_OTHER_CONTENT_PRESERVED')
    result['independent_after_completed']=True
   except BaseException as error:remember('independent_after',error)
  if session is not None and artifacts is not None:
   try:
    result['helper_after']=session.installed()
    need(result['helper_after']==result['helper_before'],'CURRENT_HELPER_CHANGED')
    result['target_after']=artifacts.after()
    need(result['target_after']==result['target_before'],'CURRENT_TARGET_CHANGED')
   except BaseException as error:remember('current_package_metadata_after',error)
  if flow is not None:
   result['actual_command_count']=flow.command_index;result['removal_action_attempted']=flow.action_attempted
   result['original_policy_counts']=dict(flow.policy.counts);result['owned_retirement_counts']=dict(flow.retirement_counts)
   try:
    need(not flow.launch_claimed and session is not None and session.nonces==set() and flow.policy.used_nonces==set(),
     'NO_NATIVE_OR_HELPER_NONCE_CONSUMPTION')
    need(flow.command_index<=42 and flow.policy.counts.get('stacks',0)<=33 and
     flow.retirement_counts.get('remove',0)<=1,'EXACT_TOTAL_RETIREMENT_BOUNDS')
    if not result['errors']:
     need(all(flow.policy.counts.get(k)==2 for k in ('target_uid','target_path','helper_uid','helper_path')) and
      sum(flow.retirement_counts.values())==flow.command_index and
      flow.policy.counts=={k:v for k,v in flow.retirement_counts.items() if k!='remove'},
      'EXACT_ORIGINAL_POLICY_AND_OWNED_COMMAND_COUNTS')
    for number in range(1,min(flow.command_index,42)+1):
     row=record_command(number)
     output=u.read(STEP/('command-%03d.stdout'%number),131072)
     if not result['errors']:qualify_joined_command(row,output,result['remove_requested'] and number==7)
   except BaseException as error:remember('complete_command_and_nonce_accounting',error)
  if artifacts is not None:
   try:
    if len(artifacts.records)==1 and 'target_after' not in result:result['failed_scope_files_revalidated']=artifacts.revalidate_files()
   except BaseException as error:remember('failed_scope_file_revalidation',error)
   try:result['target_FD_cleanup']=artifacts.close()
   except BaseException as error:remember('target_FD_cleanup',error)
  if flow is not None:
   try:flow.guard(attempted=flow.action_attempted);result['final_held_guard_passed']=True
   except BaseException as error:remember('final_held_guard',error)
   try:flow.close();result['held_binding_released']=True
   except BaseException as error:remember('held_binding_release',error)
  if guard is not None:
   try:
    result['Main_after']=guard();result['current_Main_window']=current_main_read_window(result)
   except BaseException as error:remember('independent_final_Main',error)
  for fd,name in ((action_lock,'global_action_lock'),(flow_lock,'flow_lock')):
   if fd is not None:
    try:os.close(fd);result[name+'_released']=True
    except BaseException as error:remember(name+'_release',error)
  if entry is not None:
   try:
    entry.qualified(SOURCE_MANIFEST)
    need(not os.path.lexists(FLOW/'launch-scope.json'),'ORIGINAL_LAUNCH_SCOPE_MUST_REMAIN_ABSENT')
    result['source_and_artifact_inputs_unchanged']=True
   except BaseException as error:remember('final_source_closure',error)
  if resources is not None:
   try:result['owned_after']=u.owned_resources();u.resources_qualified(resources,result['owned_after'])
   except BaseException as error:remember('final_owned_resources',error)
 complete=bool(not result['errors'] and result.get('before_tables_qualified') is True and
  result['independent_after_completed'] and result.get('final_held_guard_passed') is True and
  result.get('current_Main_window',{}).get('complete') is True and
  result['held_binding_released'] and result['flow_lock_released'] and result['global_action_lock_released'] and
  result.get('source_and_artifact_inputs_unchanged') is True and
  result.get('target_FD_cleanup',{}).get('held_APK_FDs_closed')==1 and
  (result.get('already_absent_without_removal') is True or
   (result['remove_acknowledged'] and result.get('normal_removal_verified') is True)))
 result['ok']=complete
 if complete:
  try:
   receipt={'schema':'pocket4-independent-current-IHG877-retirement-reconciliation-v2',
    'created_utc':recorder.now(),'source_sha256':source_sha256,'task':TASK,'component':COMPONENT,
    'original_action_outcome':'unknown_retained','original_launch_scope_created':False,
    'authorizes_original_action_replay':False,'native_reported_task_id':None,
    'owned_current_Android_leaf_absent':True,'all_other_current_root_and_task_content_preserved':True,
    'original_task876_disappearance_attributed':False,'entire_original_prelaunch_baseline_restored':False,
    'actual_historical_chain':result['historical_chain'],
    'independent_current_baseline02':result['independent_current_baseline02'],'before_tables':result['before_tables'],
    'independent_after':result['independent_after'],
    'command_result_pins':[{k:row[k] for k in ('path','bytes','sha256')} for row in result['command_records']]}
   ref.write_new(RECONCILIATION,receipt);raw=u.read(RECONCILIATION,65536)
   result['independent_reconciliation_receipt']={'path':str(RECONCILIATION),**pin(raw)}
  except BaseException as error:remember('new_independent_receipt',error);result['ok']=False
 result['retirement_outcome_unknown']=bool(result['removal_action_attempted'] and not result['ok'])
 if step_created:
  try:ref.write_new(STEP/'result.json',result)
  except BaseException as error:
   remember('durable_retirement_result',error);result['ok']=False
   result['retirement_outcome_unknown']=bool(result['removal_action_attempted'])
 data=(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(data)<=131072,'SAFE_RETIREMENT_OUTPUT_BOUND')
 print(data.decode(),end='',flush=True)
 return 0 if result['ok'] else 1
