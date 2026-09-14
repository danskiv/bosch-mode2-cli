# Bosch Intrusion Integration Protocol (Mode 2) — Technical Reference Specification

This document provides a comprehensive engineering guide to the **Bosch Mode 2 Automation Protocol**, used by Bosch intrusion control panels (Solution 2000/3000, AMAX Series, and B/G Series) for third-party automation, BMS, PSIM, and monitoring integrations.

---

## 1. Protocol Architecture & Transport Layer

### 1.1 Connection Parameters
* **Transport:** TCP Socket (Stream-oriented).
* **Default Port:** `7700` (Configured in A-Link Plus, RPS, or B426 web interface).
* **Security Modes:**
  * **Plain TCP:** Default and standard on Solution 2000/3000 with B426.
  * **TLS / SSL:** Supported on B-Series / G-Series panels (Certificates or self-signed).
* **Concurrency Rules:**
  * **Solution 2000 / 3000 & AMAX:** **Single In-Flight Command**. The B426 serial bridge processes one command at a time. Pipelining multiple commands causes packet drops or bus desynchronization.
  * **B-Series & G-Series (B3512 to B9512G):** **Multi In-Flight**. Supports up to 100 concurrent asynchronous requests in flight.

---

## 2. Frame Structure & Byte Layout

Each Mode 2 transmission consists of a protocol header, length indicator, opcode, and optional payload.

### 2.1 Protocol Dialects (`Protocol Byte`)

| Protocol Byte | Name | Length Field Size | Description |
| :---: | :--- | :---: | :--- |
| **`0x01`** | **Basic Protocol** | 1 byte (`0..255`) | Standard request/response frame used for commands, status, and Solution history. |
| **`0x02`** | **Unsolicited Push** | 2 bytes Big-Endian | Asynchronous notification pushed by the panel when subscribed events occur. |
| **`0x04`** | **Extended Protocol**| 2 bytes Big-Endian | Used for large data blocks (e.g. B/G Series extended event logs $>255$ bytes). |

### 2.2 Standard Request Frame (`0x01 Basic`)
```
+---------------+---------------+---------------+-----------------------+
| Protocol (1B) | Length (1B)   | Opcode (1B)   | Payload (0..N Bytes)  |
|     0x01      |  (1 + len)    |  e.g. 0x01    |  Command parameters   |
+---------------+---------------+---------------+-----------------------+
```
* **Length Byte Value:** Equals $1$ (for the Opcode byte) $+$ the number of payload bytes.

### 2.3 Panel Response Frames
When a command is sent, the panel responds with one of three response types:

#### A. Positive Acknowledgment (`0xFC - RSP_ACK`)
Returned when an action command (e.g. login, arming, output control) succeeds without data return:
```
Byte 0: 0x01 (Protocol 1)
Byte 1: 0x01 (Length = 1)
Byte 2: 0xFC (ACK)
```

#### B. Negative Acknowledgment (`0xFD - RSP_NACK`)
Returned when a command is rejected or invalid:
```
Byte 0: 0x01 (Protocol 1)
Byte 1: 0x02 (Length = 2)
Byte 2: 0xFD (NACK)
Byte 3: Error Code (1 Byte)
```

**Standard NACK Error Codes:**
* `0x00`: Non-specific / generic error
* `0x01`: Checksum or frame format error
* `0x02`: Parameter invalid or out of range
* `0x03`: Panel busy (try again later)
* `0x04`: Unauthorized / invalid PIN or passcode
* `0x05`: Command not supported in the current panel state (e.g. querying history while armed)

#### C. Data Result (`0xFE - RSP_RESULT`)
Returned when a query command succeeds with data payload:
```
Byte 0: 0x01 (Protocol 1)
Byte 1: Length (1 + payload_len)
Byte 2: 0xFE (RESULT)
Byte 3..N: Response Data Payload
```

---

## 3. Command Dictionary (Opcodes)

| Opcode | Name | Direction | Description |
| :---: | :--- | :---: | :--- |
| **`0x01`** | `CMD_WHAT_ARE_YOU` | Query | Requests panel model code, firmware protocol, and capability bitmask. |
| **`0x06`** | `CMD_AUTHENTICATE` | Action | Authenticates Automation Passcode or Installer Passcode (B/G & AMAX). |
| **`0x08`** | `CMD_ALARM_MEMORY_SUMMARY` | Query | Retrieves 8-byte summary count of active alarm memory per priority. |
| **`0x11`** | `CMD_SET_DATE_TIME` | Action | Sets internal RTC date and time on the panel. |
| **`0x12`** | `CMD_REQUEST_DATE_TIME` | Query | Reads current RTC date and time from the panel. |
| **`0x15`** | `CMD_REQUEST_RAW_HISTORY_EVENTS` | Query | Reads historical transaction log records (8 bytes per event on Sol2000). |
| **`0x20`** | `CMD_REQUEST_PANEL_SYSTEM_STATUS`| Query | Retrieves global panel firmware revision and active system faults bitmap. |
| **`0x23`** | `CMD_ALARM_MEMORY_DETAIL` | Query | Reads specific point/area identities that triggered alarm memory. |
| **`0x24`** | `CMD_REQUEST_CONFIGURED_AREAS` | Query | Returns bitmask of configured / enabled Areas (Partitions). |
| **`0x26`** | `CMD_AREA_STATUS` | Query | Reads arming and readiness status of requested Area IDs. |
| **`0x27`** | `CMD_AREA_ARM` | Action | Commands an Area to Arm Away (`0x01`), Stay (`0x02`/`0x03`), or Disarm (`0x04`). |
| **`0x29`** | `CMD_AREA_TEXT` | Query | Reads text description label configured for an Area. |
| **`0x30`** | `CMD_REQUEST_CONFIGURED_OUTPUTS`| Query | Returns bitmask of configured / enabled programmable outputs. |
| **`0x31`** | `CMD_OUTPUT_STATUS` | Query | Reads active/inactive state of programmable relay outputs. |
| **`0x32`** | `CMD_SET_OUTPUT_STATE` | Action | Activates (`0x01`) or deactivates (`0x00`) a programmable output. |
| **`0x33`** | `CMD_OUTPUT_TEXT` | Query | Reads text description label configured for an output. |
| **`0x35`** | `CMD_REQUEST_CONFIGURED_POINTS` | Query | Returns bitmask of configured / enabled physical points (zones 1..8). |
| **`0x38`** | `CMD_POINT_STATUS` | Query | Reads electrical loop status for requested point IDs. |
| **`0x3C`** | `CMD_POINT_TEXT` | Query | Reads text description label configured for a point (e.g. "Front Door"). |
| **`0x3E`** | `CMD_LOGIN_REMOTE_USER` | Action | Authenticates Solution 2000/3000 numeric User PIN (4–8 digits). |
| **`0x4A`** | `CMD_PRODUCT_SERIAL` | Query | Reads 6-byte unique panel hardware serial number. |
| **`0x5F`** | `CMD_SET_SUBSCRIPTION` | Action | Configures unsolicited event push subscriptions (B/G Series). |
| **`0x63`** | `CMD_REQUEST_RAW_HISTORY_EVENTS_EXT` | Query | Extended history query for B/G panels with large event stores. |

---

## 4. Key Handshake & Authentication Flows

### 4.1 Discovery (`CMD_WHAT_ARE_YOU - 0x01`)
1. Client sends: `01 02 01 03` (Requesting protocol version 3).
2. Panel returns `0xFE` with 64+ bytes payload:
   * **Byte 0:** Panel Model ID:
     * `0x20` = Solution 2000
     * `0x21` = Solution 3000
     * `0x22..0x24` = AMAX 2100 / 3000 / 4000
     * `0xA6` = B8512G
     * `0xA8` = B3512
   * **Bytes 5..6:** Mode 2 Protocol Version (e.g. `0x02 0x01` = v2.1).
   * **Byte 13:** Panel Busy Flag.
   * **Bytes 23..56:** Capability Bitmask (declares support for subscriptions, serial reading, CF01 vs CF03 text format, etc.).

### 4.2 Authentication on Solution 2000 (`CMD_LOGIN_REMOTE_USER - 0x3E`)
* Solution 2000 encodes the user PIN as 4 bytes in BCD/Hex padded with `0xF`.
* **Example PIN `1234`:**
  * Padded string: `"1234FFFF"`
  * Converted to 4 bytes: `0x12 0x34 0xFF 0xFF`
  * Complete TX Frame: `01 05 3E 12 34 FF FF`
* **Response:**
  * Success: `01 01 FC` (`RSP_ACK`)
  * Failed: `01 02 FD 04` (`RSP_NACK` - Unauthorized)

---

## 5. Status Enums & Data Formats

### 5.1 Point (Zone) Status Codes (`CMD_POINT_STATUS - 0x38`)
Response pairs: `[Point_ID: 2 bytes Big-Endian] [Status_Byte: 1 byte]`

| Status Code | Meaning | Physical Loop State |
| :---: | :--- | :--- |
| **`0x00`** | `Unassigned` | Point not configured in panel |
| **`0x01`** | `Short` | Loop shorted (below normal EOL resistance) |
| **`0x02`** | `Open` | Loop open / contact broken (Alarm trigger) |
| **`0x03`** | `Normal` | Loop sealed with proper End-Of-Line resistor |
| **`0x04`** | `Missing` | Wireless transmitter or expander missing |
| **`0x05`** | `Resistor 2` | Tamper condition in dual-resistor loops |
| **`0x06`** | `Resistor 3` | Fault condition in multi-state loops |
| **`0xFF`** | `Unknown` | Point status unpolled or offline |

### 5.2 Area (Partition) Arming Status (`CMD_AREA_STATUS - 0x26`)

| Status Code | Text Representation | Operational Meaning |
| :---: | :--- | :--- |
| **`0x01`** | `All On / Away Armed` | Perimeter and Interior detectors fully armed |
| **`0x02`** | `Part On Instant` | Perimeter armed without entry delay |
| **`0x03`** | `Part On Delay / Stay Armed` | Perimeter armed with entry delay; interior off |
| **`0x04`** | `Disarmed` | System disarmed; only 24Hr zones active |
| **`0x05`** | `Away Armed Entry Delay` | Entry delay timer active during Away arm |
| **`0x07`** | `Away Armed Exit Delay` | Exit delay countdown active |

---

## 6. History Transaction Log Encoding (Solution 2000)

On Solution 2000, each history record returned by `0x15` is an **8-byte packed binary structure**:

| Offset | Size | Name | Description |
| :---: | :---: | :--- | :--- |
| **0..1** | 2 Bytes (LE) | Time Word 1 | Packed bitfield: `minute:6 | hour:5 | day:5` |
| **2..3** | 2 Bytes (LE) | Time Word 2 | Packed bitfield: `second:6 | month:4 | year_offset:6` ($Year = 2000 + offset$) |
| **4..5** | 2 Bytes (LE) | Target / Area | Point number (1..8) or Area number (1..2) |
| **6** | 1 Byte | Event Code | Numeric event type (0..171) matching Bosch message table |
| **7** | 1 Byte | User Number | ID of user who initiated action (1..32) |

### 6.1 Bit Unpacking Algorithm (Python):
```python
# Unpack Time Word 1 (offset 0..1)
w1 = int.from_bytes(raw[0:2], "little")
minute = w1 & 0x3F
hour   = (w1 >> 6) & 0x1F
day    = (w1 >> 11) & 0x1F

# Unpack Time Word 2 (offset 2..3)
w2 = int.from_bytes(raw[2:4], "little")
second = w2 & 0x3F
month  = (w2 >> 6) & 0x0F
year   = 2000 + ((w2 >> 10) & 0x3F)

timestamp = datetime(year, month, day, hour, minute, second)
```

---

## 7. Official Documentation & Acquisition References

1. **Official Specification Document:**
   * **Title:** *Intrusion Integration Protocol (Mode 2) Commands available with Mode 2 Protocol*
   * **Publisher:** Bosch Security Systems / Radionix
   * **Direct URL:** `https://www.radionix.com/us/local/support/intrusion-integration-protocol-mode2.pdf`
2. **Official Technical Support Email for Protocol Clarifications:**
   * `integrated.solutions@us.bosch.com`
3. **Firmware & Engineering Software:**
   * **Bosch A-Link Plus:** For Solution 2000/3000 & AMAX configuration.
   * **Bosch RPS (Remote Programming Software):** For B-Series & G-Series configuration.
