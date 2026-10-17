#!/usr/bin/env python3
"""Capture Android guest boot-chain observations through adb.

Every command is a real observation. A failed command is written to disk and
classified as blocked; it is never converted into a synthetic success.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = [
    ("bionic", ["shell", "getprop", "ro.product.cpu.abi"]),
    ("init", ["shell", "getprop", "init.svc.bootanim"]),
    ("binder", ["shell", "ls", "-l", "/dev/binder", "/dev/vndbinder", "/dev/hwbinder"]),
    ("zygote", ["shell", "pidof", "zygote", "zygote64"]),
    ("system_server", ["shell", "pidof", "system_server"]),
    ("art", ["shell", "getprop", "dalvik.vm.usejit"]),
    ("package_manager", ["shell", "cmd", "package", "list", "packages"]),
    ("graphics", ["shell", "dumpsys", "SurfaceFlinger"]),
]


def classify(stage: str, output: str, code: int) -> str:
    if code == 0:
        return "observed"
    lowered = output.lower()
    if stage == "binder" and ("no such file" in lowered or "not found" in lowered):
        return "blocked_missing_binder"
    if stage in {"zygote", "system_server"} and ("no such process" in lowered or not output.strip()):
        return "blocked_service_not_running"
    if stage == "graphics" and ("not found" in lowered or "permission" in lowered):
        return "blocked_graphics_observation"
    return "blocked_command_failure"


def call(adb: str, serial: str | None, args: list[str]) -> tuple[int, str, list[str]]:
    command = [adb]
   -¹Ó^-¢G§²ÚîÆ­yÖÖF6‚7W'&VçB'—FW2à¢f–çFbÒVF—G5²v…ö÷7÷f–çFeöÖWFFFö6ö×F–&–Æ—G’uÐ¢6†V6¶VE÷FööÂÒF‚‡f–çFbævWB‚wFööÂrÂrr’’ç&W6öÇfR‚¢–b†æ÷B6†V6¶VE÷FööÂæ—5öf–ÆR‚’÷ ¢æ÷B6†V6¶VE÷FööÂæ—5÷&VÆF—fU÷Fò‡&ö÷Bòv÷WBö†÷7Br’÷ ¢†6…öf–ÆR†6†V6¶VE÷FööÂ’Òf–çFbævWB‚wFööÅ÷6†#Sbr’“ ¢W'&÷'2æVæB‚tõ56†V6·f–çFb†÷7B&–æ'’6†ævVBöÖ—76–ær6–æ6RfW&–f–6F–öâr¢&V6÷&FVE÷f–çFbÒf–çFbævWB‚wf–çFeöf–ÆW2rÂ·Ò¢–bæ÷B—6–ç7Fæ6R‡&V6÷&FVE÷f–çFbÂF–7B’÷"æ÷B&V6÷&FVE÷f–çFc ¢W'&÷'2æVæB‚vÖ—76–ærd”åDb6ö×F–&–Æ—G’6÷W&6Rf–ÆR–çfVçF÷'’r¢VÇ6S ¢f÷"æÖRÂ—FVÒ–â&V6÷&FVE÷f–çFbæ—FV×2‚“ ¢6†V6µ÷&V6÷&B‡&öGV7BÂwf–çFc¢r¶æÖRÂ—FVÒÂW'&÷'2À¢ÆÆ÷vVE÷7–ÖÆ–æµ÷&ö÷C×&ö÷Bòv÷WBr¢–bvW…ö–æfõ÷6†#Sbr–âf–çFc ¢F…÷FW‡BÒf–çFbævWB‚vW…ö–æfõ÷F‚rÂrr¢6öÖÖæBÒf–çFbævWB‚v6öÖÖæBrÂµÒ¢ÖVBÒf–çFbævWB‚vÖVE÷'F—F–öç2rÂ·Ò¢W…÷F‚ÒF‚‡F…÷FW‡B’ç&W6öÇfR‚’–bF…÷FW‡BVÇ6RæöæP¢–b†W…÷F‚—2æöæR÷"æ÷BW…÷F‚æ—5öf–ÆR‚’÷ ¢W…÷F‚ææÖRÒvW‚Ö–æfòÖÆ—7Bç†ÖÂr÷ ¢æ÷BW…÷F‚æ—5÷&VÆF—fU÷Fò‡&ö÷Bòv÷WBr’÷ ¢†6…öf–ÆR†W…÷F‚’Òf–çFe²vW…ö–æfõ÷6†#SbuÒ“ ¢W'&÷'2æVæB‚tU‚–æfò'—FW26†ævVB6–æ6Rd”åDb6†V6²r¢VÇ6S ¢2F†RæG&ö–BRFööÂ&VG2U‚–æfòVæFW"ÒÖF—&ÖöWƒ°¢2Fòæ÷BÆÆ÷r&WÆ’öb&W÷'BF†BW6VB&VÖ÷fVBfÆw2÷ ¢2v†÷6RF—&Ö—2æ÷BF†RVF—FVBF—&V7F÷'’à¢Ö–ærÒröWƒ¢r²7G"†W…÷F‚ç&VçB¢—'2ÒÆ—7B‡¦—†6öÖÖæBÂ6öÖÖæE³¥Ò’’–b—6–ç7Fæ6R†6öÖÖæBÂÆ—7B’VÇ6RµÐ¢–b†ÖVBævWB‚röW‚r’Ò7G"†W…÷F‚ç&VçB’÷ ¢‚rÒÖF—&ÖrÂÖ–ær’æ÷B–â—'2÷ ¢rÒÖW‚Ö–æfòÖf–ÆRr–â6öÖÖæB“ ¢W'&÷'2æVæB‚tU‚Ö–æræ÷B&÷VæBFòVF—FVB6†V6·f–çFb–çfö6F–öâr¢&W÷'E²vÆVæ6†W%÷6†#SbuÒÒ†6…öf–ÆR†ÆVæ6†W"¢–bæ÷BW'&÷'3 ¢&W÷'E²w7FGW2uÒÒw&VfÆ–v‡EööæÇ’p¢W†6WB…fÇVTW'&÷"Âõ4W'&÷"Â§6öâä¥4ôäFV6öFTW'&÷"Â7V'&ö6W72åF–ÖV÷WDW‡—&VB’2W†3 ¢W'&÷'2æVæB‡7G"†W†2’¢&WGW&â&W÷'@  ¦FVbÖ–â†&wcÔæöæR’Óâ–çC ¢Ò&w'6Rä&wVÖVçE'6W"‚¢æFEö&wVÖVçB‚rÒÖ÷7×&ö÷BrÂ&WV—&VCÕG'VRÂG—SÕF‚¢æFEö&wVÖVçB‚rÒÖWf–FVæ6RrÂ&WV—&VCÕG'VRÂG—SÕF‚¢æFEö&wVÖVçB‚rÒ×&öGV7BÖ÷WBrÂ&WV—&VCÕG'VRÂG—SÕF‚¢æFEö&wVÖVçB‚rÒÖÆVæ6†W"rÂ&WV—&VCÕG'VRÂG—SÕF‚¢æFEö&wVÖVçB‚rÒÖ÷WBrÂ&WV—&VCÕG'VRÂG—SÕF‚¢&w2Òç'6Uö&w2†&wb¢&W7VÇBÒfW&–g’†&w2æ÷7÷&ö÷BÂ&w2æWf–FVæ6RÂ&w2ç&öGV7Eö÷WBÂ&w2æÆVæ6†W"¢&w2æ÷WBç&VçBæÖ¶F—"‡&VçG3ÕG'VRÂW†—7Eöö³ÕG'VR¢&w2æ÷WBçw&—FU÷FW‡B†§6öâæGV×2‡&W7VÇBÂ–æFVçCÓ"Â6÷'Eö¶W—3ÕG'VR’²uÆâr¢&–çB†§6öâæGV×2‡²w7FGW2s§&W7VÇE²w7FGW2uÒÂvW'&÷'2s§&W7VÇE²vW'&÷'2uÒÀ¢væG&ö–Eööåö7FW&–æ5÷fW&–f–VBs¤fÇ6WÒ’¢&WGW&â–b&W7VÇE²w7FGW2uÓÓÒw&VfÆ–v‡EööæÇ’rVÇ6R  ¦–bõöæÖUõòÓÒuõöÖ–åõòs ¢7—2æW†—B†Ö–â‚’ 