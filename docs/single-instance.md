# Single-instance ownership and recovery

The application uses one `QLockFile` per resolved settings directory. The full lock path is shown in failure dialogs, stderr and the successful-start log. Different `--data-dir` folders intentionally represent separate instances; changing folders is not a way to recover the same preferences.

## Incident and resolution

The reported duplicate-launch error was reproduced against the manual-review instance left running by the agent. Its verified owner was PID **51080**, executing this project's `python -m app --data-dir .runtime\manual`. Qt returned `LockFailedError`, not `PermissionError`.

Actual lock path:

```text
C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion\.runtime\manual\application.lock
```

The default path without `--data-dir` is `C:\Users\Romcill\AppData\Local\OfflineCompanion\OfflineCompanion\application.lock`; no lock existed there during inspection.

The agent verified the owner's PID, command line, project working directory, process creation time and window title, then posted WM_CLOSE to that companion's window. It shut down normally and released its lock. No unrelated Python process was terminated, and `settings.json` was byte-for-byte unchanged. A subsequent native launch using the same settings succeeded with tray and recovery-hotkey registration, then exited cleanly. No review instance is intentionally left running after this fix.

## Current behavior

| Condition | Diagnostic and action |
| --- | --- |
| Running local owner with matching process name | **Companion already running**, with PID, application, hostname and exact path. Use its tray/hotkey, or Exit application before restarting. The rejected launch does not load or save preferences. |
| Qt `PermissionError` / folder creation denied | Access-denied message identifying the folder/file; no claim that another companion is running. Correct permissions/read-only status for that path. |
| Dead owner with a Windows read-only lock | **Stale lock is read-only**. The dead PID and read-only attribute were checked; correct that attribute and retry. No forced deletion occurs. |
| Dead owner, recoverable lock | Qt automatically recovers it during acquisition; ordinary startup proceeds. |
| Dead owner but Qt still cannot acquire | **Stale instance lock could not be recovered**; retry and inspect filesystem access. No process is killed and the file is preserved. |
| Missing/malformed owner, remote computer, inaccessible process or changed process identity | Ownership is explicitly **unverified**; preserve the lock, retry after any concurrent startup settles, and investigate the displayed path. Do not infer that a lock is stale from its age alone. |
| Directory occupies lock path or Qt reports another I/O failure | Filesystem-specific error rather than a duplicate-instance message. Check the indicated path and disk state. |

`setStaleLockTime(0)` remains intentional: the companion may run indefinitely, so elapsed time must not evict a living owner. Qt still checks dead-process ownership and performs stale-lock recovery. The application never calls `removeStaleLockFile()`, unlinks a lock itself, or terminates a process based on lock metadata. Process inspection is diagnostic; `QLockFile` remains the acquisition authority. See [Qt's locking guidance](https://doc.qt.io/qt-6/qlockfile.html).

The lock context covers logging setup, controller creation, the event loop, settings save and cleanup. It releases ownership on normal return and exceptions, including startup failures. A 100 ms acquisition timeout allows brief startup/shutdown contention without waiting indefinitely. Unverifiable or malformed locks are deliberately not automatically overridden; that is a safety limitation, not permission to disable protection.

No server, socket, additional persistent process or new dependency was introduced. Duplicate launches do not send messages to an existing instance. Dismissing a duplicate-launch dialog exits only the rejected launch; the existing companion keeps running.

## Resume manual acceptance

```powershell
cd C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion
.\.venv\Scripts\python.exe -m app --data-dir .runtime\manual
```

Launch once. For a subsequent restart, use **Exit application** in the existing tray first. The tray can be in Windows' overflow area. **Ctrl+Alt+Shift+R** restores interaction when its hotkey registered. Keep the same data directory to retain existing settings.

To check duplicate protection manually, leave that instance running and execute the same command again. Expect a dialog naming the existing PID and exact lock path. Dismiss it and confirm the original companion still responds. Exit through the original tray and launch again: the new launch must succeed and restore preferences. Continue the other [Phase 2 manual checks](phase-2-validation.md).

## Regression coverage

`tests/test_instance.py` adds separate-process race, live-owner, real crash, release/relaunch and real Windows read-only stale-lock tests. It also covers malformed owners, error classification, settings preservation, application duplicate dialogs, log/config startup failures, event-loop exit/restart and tray-action exit. Permission-denied directory creation, Qt `PermissionError`, and generic I/O errors are additionally fault-injected; no user-folder ACLs are changed to test them.

The tray/hotkey Windows integration tests still verify recovery action dispatch, native input styles, actual hotkey registration and native-message recovery. They do not replace physical keyboard/tray observations. Phase 3 remains stopped until Phase 2 manual acceptance succeeds and the user authorizes it.
