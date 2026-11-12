"""Frames captured from a live JG Aura system (SAL01 stick and SALJG30 gateway)."""

# Study bathroom (cloud id d5ea) status: Frost, room 19.0, target 5.0.
STATUS_STUDY_BATHROOM = bytes.fromhex(
    "7c590600ead500000042312529462a30303030224f464e2a6645463f6320203f502c45463f632020"
    "3f502c45463f6320203f502c45463f6320203f502c45463f6320203f502c51573f63202039502c51"
    "573f63202039502c3a"
)
# Downstairs bathroom (cloud id bea0) status after Medium: room 18.5, target 18.0.
STATUS_DOWNSTAIRS_MEDIUM = bytes.fromhex(
    "7c594900a0be00000042312425454430303030224c44482a664b573f6320203d502c4b573f632020"
    "3d502c4b573f6320203d502c4b573f6320203d502c4b573f6320203d502c51573f63202039502c51"
    "573f63202039502c2e"
)
# Gateway command to the study (b7b0): preset Medium, counter 1.
GATEWAY_SET_MEDIUM = bytes.fromhex("7c111100b0b7000000413201423035256b")
# Gateway command to the study: Away for 01, counter 6.
GATEWAY_SET_AWAY = bytes.fromhex("7c131c00b0b70000004132064230352830316f")
# Stick confirmation of the Medium command.
CONFIRM_MEDIUM = bytes.fromhex("7c112500b0b7000000423301423035255d")
# Stick receipt for a host request with seq 0x2f.
RECEIPT = bytes.fromhex("7c0d2f00ead500000020320073")
# Gateway acknowledging a status report.
GATEWAY_ACK = bytes.fromhex("7c0d0600ead500000020310059")
# Device list answer: CF B2 plus the 11 thermostats.
DEVICE_LIST = bytes.fromhex(
    "7c480300000000000042b4cfb2a0be783a122aa7d1792192969dcfd2e4ead5b0b75df0"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff03"
)
# Gateway asking every thermostat to report (sent to FFFF at startup).
GATEWAY_REPORT_REQUEST = bytes.fromhex("7c0e0100ffff0000004130003032")
# Gateway telling the thermostats it is online.
GATEWAY_ONLINE = bytes.fromhex("7c0d1200000000000041b031a3")
# Gateway time sync for 2026-10-28 08:32:57 UTC, a Wednesday.
GATEWAY_TIME_SYNC = bytes.fromhex("7c130c00000000000041bdb96f7432030d0001")
# Gateway time sync for 2026-10-30 09:07:40 UTC, a Friday: the same 03 0D 00 ending.
GATEWAY_TIME_SYNC_FRIDAY = bytes.fromhex("7c130800000000000041bddc1a7732030d0016")
