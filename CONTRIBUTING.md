# Contributing

Useful contributions include independently reproduced examples, extraction fixes, reviewed animation components, and speech/alignment adapters.

For a bug report, provide the command, Python and package versions, operating system, expected and observed output, and a minimal input you have permission to share. Do not attach private papers, credentials or cloned voice references.

For an example, include the input and its rights, script, source-to-claim links, actual outputs, reproduction steps, and completed versus unperformed checks. Synthetic examples must be labelled synthetic. A working renderer does not certify scientific accuracy.

Keep changes local. Run `python -m unittest discover -s tests -v`, then reproduce the affected example. A new dependency should solve a concrete need and have a documented fallback. Do not add a provider setting unless actual code uses it.

This release is a workflow skill with a deterministic demonstration. Universal PDF rendering and interchangeable TTS providers are not implemented yet.
