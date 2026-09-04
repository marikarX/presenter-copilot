# M9 Clean Windows Machine Checklist

This procedure requires a disposable Windows VM or a fresh standard-user
profile. It is intentionally manual because the repository scripts must not
mutate a developer machine.

1. Record the installer filename, SHA-256, and source commit SHA.
2. Run the unsigned per-user installer and choose an explicit install folder.
3. Confirm no Python, uv, repository, `PYTHONPATH`, or developer-mode override
   is required to launch the application.
4. Create a local project and verify the core health/status path.
5. Import only the checked-in synthetic fixture; verify transcript authorization
   disclosure precedes the native picker.
6. Verify models show an explicit prepare action and no silent launch download.
7. Exercise typed Teach/Challenge, Run, and Live Assist deterministic/manual
   paths where the packaged test environment supports them.
8. Export diagnostic metadata: preview it first and confirm it contains no
   source text, transcript text, secrets, prompts, raw provider errors, or
   arbitrary filesystem paths.
9. Delete a project and confirm it is absent from the project list and cannot
   be queried after restart.
10. Uninstall. Confirm the application is removed while user data remains.
11. Reinstall to a different explicit directory and confirm retained local
    data opens without a silent model download.
12. Record any unavailable microphone, model, provider, PowerPoint, GPU,
    compositor, or external-capture evidence separately.

Use `scripts/clean-machine-checklist.ps1` only as a read-only artifact and
instruction reporter. It does not perform installation, uninstallation, or
data deletion.
