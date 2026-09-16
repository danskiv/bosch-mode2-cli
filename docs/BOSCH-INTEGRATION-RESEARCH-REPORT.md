# Bosch Intrusion Integration Research Report

**Scope:** Solution 2000 + B426/B426-M + Mode 2 / A-Link / RSC+ integration, with emphasis on a read-focused portable integration client.

**Research date:** 2026-09-15

**Target observed in the lab:** Solution 2000 with a unit identified as standard B426, firmware `03.15.100`, endpoint `192.168.1.55:7700`. The observations in this report are laboratory facts from the current project, not vendor claims.

> **Security boundary:** This report intentionally omits PINs, installer codes, A-Link passwords, web passwords, tokens, certificates, and other credentials. No credential should be stored in source, fixtures, command history, portable packages, or diagnostic logs.

## 1. Executive conclusion

The proposed integration is technically plausible, but the current failure is not yet attributable to the laptop. The strongest evidence is that both Windows and Ubuntu reached the B426 transport layer, while the Mode 2 identity exchange did not yield a valid parsed application response. The next investigation must therefore prioritize panel/module commissioning, exact Solution firmware and network-module state, protocol/mode selection, and single-session conflicts before changing operating-system networking.

The project must distinguish at least six gates:

1. **Physical/bus:** B426 is powered, correctly wired to the panel bus, addressed correctly, and supervised by the panel.
2. **Network:** the client reaches the configured B426 IP and port.
3. **Transport security:** the endpoint expects plain TCP or TLS, and the client selects the matching transport.
4. **Mode 2 framing:** the client sends and parses the Mode 2 application frame, rather than merely opening a socket.
5. **Identity/capabilities:** `WHAT_ARE_YOU` returns a valid panel model/protocol/capability response.
6. **Authentication and authorization:** the Solution user can authenticate; history additionally depends on the required authority.

The successful completion of one gate does not prove the next gate. In particular, TCP reachability and TLS handshake success do not prove Mode 2 identity or authentication.

## 2. What Bosch officially exposes

Bosch/Keenfinity publishes several different integration paths, and they should not be treated as interchangeable:

| Path | Primary purpose | Scope found in sources | Relevance |
|---|---|---|---|
| A-Link Plus | Programming, upload/download, and direct/network administration of Solution panels | Solution 2000/3000 documentation describes A-Link Plus and network-module programming | Configuration oracle and known-good comparison, not the target standalone API [1][10] |
| RSC+ | Mobile remote control for supported Solution deployments | Bosch material ties RSC+ to cloud-connected communication modules, especially B426-M/B450-M/B443 | Not evidence that local Mode 2 is enabled [11] |
| Mode 2 | Third-party monitoring/control protocol | Bosch’s public Mode 2 command document lists identity, authentication, status, history, area/point/door functions, and control operations, but the retrieved document explicitly describes B/G Series [9] | Target protocol, but Solution-specific behavior needs exact documentation or verified implementation evidence |
| Intrusion SDK | Higher-level Windows SDK | Bosch datasheet lists monitoring/control functions for B/G panels and says it is available through the Integration Partner Program [14] | Alternative for B/G, not a drop-in replacement for a portable Solution 2000 client |
| RPS API / WebConnect | B/G programming integration | Keenfinity lists it separately from Mode 2 and SDK [8] | Not the same interface as the local Mode 2 monitor |

The official Bosch integration-tools page explicitly tells developers to choose among Mode 2, the Intrusion SDK, and the RPS API according to the use case. That separation is important: a configuration API, a high-level SDK, and a panel automation protocol have different prerequisites and capabilities [8].

## 3. Solution 2000/3000 and B426/B426-M compatibility

The current Solution 2000/3000 installation manual identifies Ethernet communication modules as accessories and describes the network module as supporting remote administration/control, mobile applications, and building-automation/integration applications [1]. The same manual distinguishes the B426-M/B450-M configuration path and documents panel capacity and module addressing for the Solution family [1]. A separate Bosch setup guide describes the B426 IP-module installation flow: power down before wiring, temporarily use the module's configuration address/mode, enable the panel network module, configure the B426 web/network settings, enable Web & Automation Security, and then return the module to its operating address/mode [10].

This creates an important model distinction:

- **Standard B426** and **B426-M** are not safe substitutes in a configuration table.
- `Network Module = Used – B4xx-M` and the cloud/RSC+ settings are associated with the B426-M path in Bosch material [11].
- The `0081 = 3` value appears in B426-M/cloud-oriented documentation and in the Home Assistant reset recipe; it must not be copied to a standard B426 without an exact panel/module/firmware match [11][7].
- The separate Bosch IP-module setup guide for Solution 2000/3000 describes enabling the IP module during initial installation and then enabling Web & Automation Security; it does not establish that every B426 firmware uses the same panel-location value for every mode [10].

The current unit has been identified as a standard B426 rather than B426-M. Therefore, the project must not use a B426-M/cloud setting as a generic Mode 2 prerequisite. The exact live panel programming and the module's live Web & Automation Security value remain material unknowns.

A manufacturer product manual also lists Solution 2000/3000 among compatible control panels and identifies the B426-M as recommended for AMAX and Solution series in the relevant product family [2]. That is evidence of product compatibility, not proof that a particular firmware combination exposes the exact same local Mode 2 behavior as the open-source client.

## 4. A-Link, RSC+, Legacy TCP, and Mode 2 are different layers

### A-Link Plus

A-Link Plus is a Bosch configuration/administration application. The Solution IP-module guide describes creating a customer, selecting the Solution panel type, using a direct connection for initial programming, configuring Network Module 1, saving/downloading panel data, and then using the network module for remote operation [10]. A-Link success proves that a particular application path and panel database/configuration are usable; it does not prove that a custom Mode 2 client has selected the same framing, authentication, or transport.

### RSC+

RSC+ is a separate remote-control application. Bosch’s cloud-connection material describes cloud connection settings for the B426-M path, including the module type and cloud connection option [11]. RSC+ reachability or successful use must not be treated as proof that local Mode 2 identity will respond.

### Legacy Panel Mode

Keenfinity documents Legacy Panel Mode as an emulation setting for older legacy panels/datagrams and explains that its configuration availability depends on module addressing [12]. Therefore, `Legacy Panel Mode = Disabled` is useful evidence that the module is not intentionally emulating that legacy path, but it is not by itself proof that Mode 2 is enabled.

### Web & Automation Security and Encryption Enable

Keenfinity's web-access documentation states that the Web & Automation Security setting determines whether the module web interface is accessed over HTTPS or HTTP [13]. Bosch's security advisory separately recommends enabling Web & Automation Security, keeping the device off the public Internet, and using firewalling/network isolation [3]. This setting should be recorded separately from an application-level `Encryption Enable` field and separately from whether the Mode 2 application protocol is actually active.

The project must record a complete configuration tuple rather than a single boolean:

```text
module model: B426 or B426-M
module firmware:
panel model and firmware:
panel network-module registration/address:
module operating address:
legacy TCP automation:
legacy panel mode:
Web & Automation Security:
Encryption Enable:
configured automation/RPS port:
active A-Link/RSC+/cloud session:
```

## 5. Mode 2 protocol evidence

The official public Mode 2 overview lists the conceptual command set: identify panel, authenticate, request protocol version and capacities, read date/time, retrieve raw/text history, request panel status, inspect alarm/trouble conditions, read areas and point status, change area arming state, and inspect door status [9]. It also states that the detailed protocol documentation is requested through Bosch integration support [9].

The strongest publicly inspectable implementation evidence is the current `mag1024/bosch-alarm-mode2` source:

- It identifies Solution 2000/3000/4000 as theoretically supported and states that the library has been tested with Solution-family panels, while warning that additional panels may need development [4].
- Its `Panel._basicinfo()` sends `WHAT_ARE_YOU` before authentication, uses the returned model/capability data to select behavior, and falls back to a second identity form if necessary [5].
- Its `Connection.send_command()` wraps requests in a Mode 2 frame and permits only one in-flight command by default; Solution and AMAX are not treated like B/G panels with broad command pipelining [6].
- For Solution panels, the library uses a numeric user code as the panel credential and does not require the B/G automation code path [4][5].
- History retrieval is attempted only when areas are disarmed, and the library warns that the user needs `master code functions` authority for history [4][5].
- The implementation supports status updates through subscription when the panel advertises the capability and otherwise falls back to polling [5].

This has a direct implication for the current diagnostic work: sending an isolated guessed `CF01` or `CF03` byte sequence is not equivalent to executing the complete upstream Mode 2 handshake. The probe must preserve the upstream frame format, TLS/plain transport choice, fresh connection behavior after a socket-closing fallback, and one-command-at-a-time discipline.

The upstream library's public README is intentionally qualified: it says “theoretically” for the model list and “in practice” for models actually tested [4]. That makes it a valuable engineering reference, but not a substitute for a Bosch-supplied Solution-specific protocol specification.

## 6. Authentication and authority model

The public Home Assistant Bosch Alarm documentation confirms the panel-family distinction:

- Solution panels use the configured Solution user code.
- B/G panels use the automation code.
- AMAX uses both according to the integration's panel-family handling [7].

The upstream library makes the same distinction in executable code [5]. For Solution history, the relevant user must have the required authority; a successful login alone is not proof that history access will work [5][7].

The integration should therefore report separate results:

```text
identity: PASS/FAIL
authentication: PASS/FAIL
area status: PASS/FAIL
point status: PASS/FAIL
history permission: PASS/FAIL/NOT TESTED
live subscription: PASS/FALLBACK POLLING/NOT ADVERTISED
```

It must never report “connected” merely because a socket exists. The portable CLI should request credentials interactively or through a local environment/masked mechanism and redact all logs.

## 7. Status, history, and live events

The upstream implementation exposes area, point, output, door, alarm-memory, panel-fault, date/time, and history operations, with status subscriptions where supported [5]. The Home Assistant integration maps these into an alarm-control-panel entity, point binary sensors, area readiness/fault sensors, alarm/trouble/supervisory sensors, and output switches [7]. It also documents a 30-second update cycle with push updates on newer devices/firmware and polling fallback otherwise [7].

For this project, the safest MVP order is:

1. Identity/capability read.
2. Read-only panel status.
3. Read-only area and point status.
4. Read-only panel faults and alarm summary.
5. Read-only history, only after authority and disarmed-state behavior are verified.
6. Live subscription if advertised; otherwise bounded polling.
7. Control operations only after a separate approval and safety test plan.

Arming, disarming, output actuation, detector reset, bell test, and test-report commands are consequential. The public Mode 2 command list includes such operations [9], but the initial product should keep them disabled or behind an explicit safety gate.

## 8. Why the current real-panel failure is still unresolved

### Observed facts in this project

- The B426 web/network endpoint is reachable.
- TCP connection to port 7700 succeeds.
- TLS negotiation has succeeded and the certificate chain identifies Bosch.
- The same general identity tests failed from Windows and Ubuntu on the same physical installation.
- No valid parsed Mode 2 identity frame has been verified.
- The current unit was identified as standard B426, firmware `03.15.100`, not B426-M.
- A-Link behavior has varied by laptop/session, and direct Mode 2 has not yet been proven from the known-good A-Link laptop.

### Ranked hypotheses

1. **Panel/module commissioning mismatch after reset — high.** The panel may have a reachable network module but an incorrect/disabled application registration or incomplete configuration. Home Assistant documents that a Solution panel can remain unreachable through Mode 2 because of incompatible configuration or a network-module state bug [7].
2. **Wrong application transport/mode — high.** The module may accept TLS while the selected listener/application path is not the same Mode 2 path expected by the upstream client. Web & Automation Security, Legacy TCP Automation, and Encryption Enable must be checked as separate values [10][12][13].
3. **Single-session lockout or stale network-module state — high.** Home Assistant documents older Solution/AMAX network stacks that support only one connection and can lock up when another cloud/integration session is active [7].
4. **Exact firmware/protocol compatibility gap — medium.** The upstream project says Solution support exists in practice but also warns that additional support can require development [4]. There is no public evidence found that explicitly certifies the exact pair “Solution 2000 firmware X + standard B426 firmware 03.15.100 + this Mode 2 client.”
5. **Host OS/network adapter issue — now lower.** Cross-OS reproduction with TCP/TLS success lowers, but does not mathematically eliminate, the host hypothesis.
6. **Credential/authority issue — not yet testable at the current gate.** Because identity has not been verified, sending or changing credentials would be premature and unsafe.

## 9. Security findings

Bosch published a security advisory for B426-family products covering a high-severity web-session issue and a cleartext-password issue on older HTTP configurations. The advisory recommends fixed firmware, firewalling, no direct Internet exposure/port forwarding, network isolation where appropriate, and enabling Web & Automation Security [3].

The observed B426 firmware `03.15.100` is newer than the older vulnerable versions listed in the advisory, but the exact patch status should still be checked against the current Bosch product catalog and release notes. “Newer than the affected version” is not the same as a complete current-security certification.

Recommended deployment boundary:

- Keep B426 on a private alarm VLAN or dedicated LAN segment.
- Permit the monitor only from an allow-listed host/IP.
- Do not forward port 7700 or web administration directly to the Internet.
- Use HTTPS for B426 web administration when the module supports/enforces it.
- Close A-Link/RSC+/web sessions before a direct diagnostic probe.
- Keep one active panel connection during commissioning tests.
- Redact credentials and raw authentication payloads from captures and logs.
- Treat the monitor as read-only until write operations are explicitly approved.
- If the system is connected to a monitoring center, coordinate any reboot, panel reset, module restart, firmware update, or test-report action with the operator.

## 10. Recommended experimental plan

### Phase A — no panel mutation

1. From the laptop where A-Link is known to work, close A-Link and all other panel applications.
2. Run only the portable identity probe, first using the same host/port and source interface that A-Link uses.
3. Capture only transport metadata and redacted application bytes; do not record credentials.
4. Verify whether the endpoint responds with a valid Mode 2 frame, a protocol NACK, a clean close, or a timeout.
5. Repeat once from the Ubuntu host, with no simultaneous connection.
6. Compare the two results byte-for-byte at the transport and application layers.

### Phase B — configuration readback

Using the B426 web UI or A-Link, record the configuration tuple in Section 4 without changing values. Confirm:

- exact module model;
- exact module firmware/build;
- exact panel model/firmware;
- module address and panel registration;
- Web & Automation Security;
- Encryption Enable;
- Legacy TCP Automation Enable;
- Legacy Panel Mode;
- configured port;
- whether a cloud/RSC+/A-Link session is active.

### Phase C — bounded restart only

If the panel owner/operator approves it, perform one documented network-module restart using the exact current Solution manual and keypad type. Do not run an unverified factory reset. Record pre/post state and allow the documented reboot/apply interval before retesting [1][7].

### Phase D — authentication and read-only data

Only after identity succeeds:

1. Authenticate with the intended Solution user through a local masked prompt.
2. Read configured areas and point list.
3. Read status.
4. Test history only while disarmed and with the required user authority.
5. Test push subscription; if unsupported, use bounded polling.
6. Keep write commands disabled.

## 11. Changes recommended for the project

### Required before declaring production readiness

- Replace default credential values in code and examples with empty placeholders and local prompt/environment input.
- Ensure all logs redact user codes and authentication payloads.
- Keep `--no-tls` as an explicit diagnostic option, not the default production path.
- Make the transport result explicit: `plain TCP`, `TLS`, certificate accepted/rejected, and application frame parsed/not parsed.
- Implement a strict Mode 2 frame parser and show raw bytes only when the user explicitly requests a redacted diagnostic mode.
- Use a fresh connection after an identity fallback that closes the socket.
- Enforce one in-flight request for Solution/AMAX family.
- Separate identity, authentication, status, history, and subscription outcomes in the CLI exit/report model.
- Remove or clearly mark any protocol details in `docs/BOSCH-MODE2-PROTOCOL-SPEC.md` that are derived from reverse engineering or the open-source client rather than verified Bosch documentation.
- Add a compatibility matrix with evidence links instead of one generic “B426 compatible” label.

### Portable Windows package

The portable package is appropriate for field testing because the end user does not need Python or pip. It must not contain configuration secrets, and the probe should be run before the full client. The package should be treated as a diagnostic tool until a real panel returns verified identity and read-only status.

## 12. Adjudicated findings from the second research pass

A newer certified integration guide gives a materially stronger mapping for the B426 web settings: **Mode 1** uses `Legacy TCP Automation = Yes` and `Web & Automation Security = Disable`, while **Mode 2** uses `Legacy TCP Automation = No` and `Web & Automation Security = Enable`. It also specifies `Encryption Enable = No` for the automation configuration and recommends `Panel Programming Enable = No` so the panel does not overwrite custom module settings.[15] This is consistent with the B426 manual's distinction between legacy unsecured automation and enhanced Automation security, and it is directly relevant to the current unit because its previously recorded `Legacy TCP Automation Enable` value was `Yes`.[1]

This does not prove that changing the setting will solve the panel, and no setting should be changed blindly. It does, however, move **transport/application-mode mismatch** to the highest-ranked testable hypothesis. The safe next step is a readback of the live value, followed—only with approval and an operator window—by changing one parameter at a time and retesting with a fresh connection.

The authentication opcode dispute is resolved in favor of the source implementations that can be inspected directly: both the current upstream library and the older Solution-specific implementation define `LOGIN_REMOTE_USER` as `0x3E`.[5][16][17] The sub-agent summary's `0x25` claim is rejected as unsupported. The older Solution implementation also sends the basic `WHAT_ARE_YOU` request directly and uses a fresh reconnect path after a connection error.[16][17] Therefore, the client should not send any guessed `0x25` login frame.

The upstream modern client currently attempts the extended identity form and falls back to the basic form on the same logical connection.[5] Because the underlying transport can be closed by a panel/module after an unsupported or malformed request, our diagnostic client should implement fallback as **close → establish a new transport → send CF01**, with a per-command timeout and a clear result (`response`, `NACK`, `EOF`, or `timeout`). This is a client-hardening recommendation based on the combined source comparison, not a claim that every B426 firmware closes on CF03.

## 13. Factory-default research update

The post-reset evidence changes the diagnosis materially: after the web Factory Default action, the module temporarily appeared at AutoIP `169.254.1.1`, accepted TLS 1.2 on port 7700, and returned valid `0xFE` identity responses identifying Solution 2000 (`0x20`) to both CF01 and CF03. Plain TCP timed out. These are laboratory observations from this project, not vendor claims.

### 13.1 Web Factory Default versus hardware recovery

Bosch's B426 Installation and Operation Guide says the web Factory Default page returns **all configuration options** to factory values, may terminate the current web session, and can be followed by the compatible control panel overwriting the defaulted module settings. Bosch specifically advises setting `Panel Programming Enable` to `No` after restoring defaults and before `Save and Execute` if the operator needs to prevent that overwrite.[1]

Keenfinity's recovery article describes a separate hardware procedure: power down for at least 30 seconds, install/short the MODE jumper, set the address dial to 9, connect a PC directly, wait for AutoIP, configure through `169.254.1.1`, then power down again, remove the MODE jumper, and restore the desired address.[18] This is not equivalent to briefly shorting two pins while the module is powered. The Bosch Solution 2000/3000 IP-module guide gives the same commissioning pattern—address 9 and MODE for configuration, then return to the operating address and normal jumper position—and describes enabling Web & Automation Security before assigning the production network settings.[10]

Therefore, the MODE jumper is a controlled recovery/commissioning mechanism, not a requirement for the Mode 2 application protocol. The project's successful post-reset CF01/CF03 exchange is direct evidence that no additional MODE-jumper reset is needed for the current diagnostic gate.

### 13.2 Why the web login can return to the login page

There is a material version conflict in the publicly available documentation. The older B426 Installation and Operation Guide lists `[REDACTED]` as the default Web Access Password and describes it as the default value.[1] The newer B426/B426-M Quick Installation Guide states that **B426 firmware v3.09+ uses the unique passcode printed on the product label**, while earlier firmware uses `[REDACTED]`.[19] The observed unit is recorded as standard B426 firmware `03.15.100`, so the newer firmware-specific rule has higher evidentiary weight for this unit.[19]

This explains the observed behavior more directly than the earlier browser/session hypothesis: the login page loads, but an old generic password is rejected and the legacy UI returns to the login page. It also explains why the behavior reproduced from Windows and a private browser window. The unique passcode is a credential and must not be copied into chat, source, screenshots, command history, or this report.

A second independent mechanism remains possible: after Factory Default, a compatible panel with `Panel Programming Enable` active can overwrite module parameters.[1] That can change Web Access Enable, Web & Automation Security, network values, or the web password after the reset. The correct troubleshooting order is therefore: verify the exact firmware/model and product-label password locally, then determine whether the panel rewrites settings; do not infer either mechanism from a browser redirect alone.

### 13.3 What “overwrite” means in this installation

The sources identify three distinct configuration-ownership paths, and they must not be conflated:

1. **Panel PnP/automatic programming:** Bosch says a configured compatible panel stores module settings and automatically programs a connected B426; `Panel Programming Enable = No` is the module-side control that prevents that automatic programming.[1]
2. **A-Link download:** the Solution 2000/3000 guide describes changing Network Module parameters in A-Link Plus and then selecting `Download to Control Panel`; the panel database then becomes the source for those downloaded network-module values.[10][20]
3. **Manual Mode 2/module configuration:** the newer integration procedure sets `Web Access Enable = Yes` and `Panel Programming Enable = No`, then configures `Legacy TCP Automation = No`, `Encryption Enable = No`, and `Web & Automation Security = Enable`. It explicitly says disabling panel programming preserves custom module settings when the panel is connected.[21]

Keenfinity separately documents the ownership consequence: after `Panel Programming Enable` is set to `No`, B426 settings can appear greyed out in RPS and must be edited again through the module web interface if panel programming is to be re-enabled.[22] This means “overwrite” may be a panel PnP write, an A-Link download to the panel, or a deliberate change of configuration authority—not necessarily a spontaneous reset of the web password.

For this project, the decisive test is a controlled before/after readback: record the live B426 tuple immediately after recovering web access, power/connect the panel in a maintenance window, then read the tuple again without changing values. A changed value proves a write occurred; it does not by itself identify whether PnP or A-Link caused it. Do not disable both Web Access and Panel Programming: Genetec warns that this locks the operator out of the module configuration.[21]

### 13.4 Factory-default parameter and operational impact matrix

| Area | Evidence-based effect or risk |
|---|---|
| Network address | Factory defaults enable DHCP/AutoIP; without DHCP the module can fall back to temporary AutoIP `169.254.1.1`.[1] |
| Automation transport | Factory defaults include port 7700 and disable Legacy TCP Automation; Web & Automation Security is a separate setting that enables HTTPS and TLS Automation.[1] |
| Web access | Web Access Enable and Panel Programming Enable govern whether web configuration and panel overwrite remain available.[1] |
| Panel interaction | A compatible configured panel can overwrite a defaulted module; Bosch explicitly warns about this.[1] |
| Hardware recovery | MODE plus address 9 is a power-cycle recovery/commissioning sequence, not a live short test.[18][10] |
| Credential | Firmware v3.09+ B426 uses the unique product-label passcode according to the newer guide; do not assume `[REDACTED]` on firmware `03.15.100`.[19] |
| Mode 2 result | This project's post-reset TLS identity response is evidence that the reset changed the effective application path, but it does not identify which individual setting caused the change. |

### 13.4 Revised conclusion and safe next gate

Do not factory-reset again and do not short MODE merely to solve the login problem. When the equipment is powered on again, use a direct isolated Ethernet connection and the exact **B426 product-label passcode** locally; do not send it to the assistant. If local login still fails, record whether the panel is connected during the attempt and treat panel overwrite as the next hypothesis. Preserve the successful post-reset identity evidence, then assign a static production IP only after configuration access and recovery are confirmed.

## 14. Final assessment

The target architecture remains viable, and the post-reset identity result is now a verified lab milestone. The current evidence no longer supports treating the failure as a generic laptop, Windows, or browser problem. The highest-value next action is a controlled configuration-recovery session: use the firmware-appropriate local web credential, document the live B426 settings, confirm whether the panel overwrites them, and then repeat the read-only Mode 2 status gate. Do not change keypad locations, force B426-M values onto a standard B426, send credentials blindly, or run another factory reset.

## Sources

[1] https://cdn.commerce.boschsecurity.com/public/documents/Solution2k3k_Installation_Manual_enUS_101593043339.pdf — Bosch Solution 2000/3000 Installation Manual
[2] https://cdn.adiglobaldistribution.us/pim/Original/10046/Upload_DS-B426_ProductManual.pdf — Bosch B426 Product Manual
[3] https://psirt.bosch.com/security-advisories/bosch-sa-196933-bt.html — Bosch B426 Security Advisory
[4] https://raw.githubusercontent.com/mag1024/bosch-alarm-mode2/master/README.md — mag1024/bosch-alarm-mode2 README
[5] https://raw.githubusercontent.com/mag1024/bosch-alarm-mode2/master/bosch_alarm_mode2/panel.py — mag1024/bosch-alarm-mode2 panel implementation
[6] https://raw.githubusercontent.com/mag1024/bosch-alarm-mode2/master/bosch_alarm_mode2/connection.py — mag1024/bosch-alarm-mode2 transport implementation
[7] https://www.home-assistant.io/integrations/bosch_alarm — Home Assistant Bosch Alarm integration documentation
[8] https://www.keenfinity-group.com/us/en/partners/technology-partners/integration-tools — Keenfinity integration tools
[9] https://www.radionix.com/us/local/support/intrusion-integration-protocol-mode2.pdf — Bosch/Radionix Intrusion Integration Protocol Mode 2 overview
[10] https://media.boschsecurity.com/fs/media/pb/media/products_1/intrusion_alarm_systems/programming_reference_guides/install-configure-solution-2000-3000-ip-module.pdf — Bosch Solution 2000/3000 IP module setup guide
[11] https://media.boschsecurity.com/fs/media/pb/media/products_1/intrusion_alarm_systems/programming_reference_guides/cloud-connection-for-rsc-app.pdf — Bosch cloud connection guide for RSC+
[12] https://knowledge.keenfinity-group.com/intrusion-alarm-systems/article/how-to-change-legacy-mode-in-the-ip-communicator — Keenfinity Legacy Panel Mode guide
[13] https://knowledge.keenfinity-group.com/intrusion-alarm-systems/article/how-to-access-the-ip-communicator-web-browser — Keenfinity B426 web-access/security guide
[14] https://media.boschsecurity.com/fs/media/pb/media/partners_1/integration_tools_1/developer/INT-SDK_Intrusion_Integration_SDK_Datasheet.pdf — Bosch Intrusion Integration SDK datasheet
[15] https://techdocs.genetec.com/r/en-US/Bosch-Intrusion-Panel-Extension-Guide-4.4.1/Enabling-communication-with-Security-Center-using-the-B420-or-B426-Ethernet-module — Genetec B426 Mode 2 configuration guide
[16] https://github.com/sanjay900/solution3000-home-assistant/blob/master/custom_components/solutions3000/solution3000.py — Sanjay Solution 2000/3000 implementation
[17] https://github.com/nicsuzor/boschalarm/blob/master/boschalarm/main.py — Nicsuzor early Bosch Solution API
[18] https://knowledge.keenfinity-group.com/intrusion-alarm-systems/article/how-to-restore-the-b42x-card-back-to-default-value — Keenfinity B42x hardware default/recovery procedure
[19] https://www.securitywholesalers.com.au/wp-content/uploads/2023/10/B426_Quick_Installation_Guide_enUS_11017149323.pdf — B426/B426-M Quick Installation Guide
[20] http://op-tech.com.au/wordpress/wp-content/uploads/2022/05/op-tech-australia-BOSCH-Solution-2000_3000__Quick_Installation_Guide_enUS.pdf — Bosch Solution 2000/3000 Quick Reference Guide
[21] https://techdocs.genetec.com/r/en-US/Security-Center-SaaS-Setup-Guide/Enabling-communication-with-Security-Center-SaaS-using-the-B426-Ethernet-module?contentId=hFw8GJBNfhRcJKwziU4hxA — Genetec B426 Mode 2 configuration guide
[22] https://knowledge.keenfinity-group.com/intrusion-alarm-systems/article/b420-or-b426-settings-are-greyed-out-in-rps — Keenfinity B420/B426 Panel Programming Enable behavior
