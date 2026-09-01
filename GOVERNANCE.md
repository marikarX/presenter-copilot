# Governance

Presenter Copilot is currently a maintainer-led pre-1.0 project.

## Decision model

The project maintainer is responsible for final decisions on:

- product scope;
- architecture;
- security/privacy posture;
- releases;
- licensing and trademarks;
- maintainer access;
- contribution acceptance.

The goal is not centralized decision-making forever; it is to keep early product direction coherent while the core architecture is still unstable.

## How decisions should be made

For meaningful technical or product decisions:

1. describe the problem and constraints;
2. identify realistic alternatives;
3. document important privacy, security, performance, and maintenance implications;
4. choose the smallest reversible decision when uncertainty is high;
5. record durable decisions in `docs/DECISIONS.md` or a future ADR.

## Maintainers

Maintainer responsibilities include:

- reviewing and merging contributions;
- triaging security reports;
- keeping releases and documentation coherent;
- enforcing the Code of Conduct;
- avoiding unnecessary lock-in to one model provider or platform;
- protecting the local-first privacy model from accidental regression.

Additional maintainers may be added based on sustained high-quality contribution and demonstrated judgment.

## Compatibility and breaking changes

Before 1.0, APIs, configuration, storage formats, and architecture may change without backwards compatibility guarantees. Breaking changes should still be documented clearly in the changelog.

After 1.0, the project should define explicit compatibility and deprecation policies.

## Commercial relationship

If commercial services or enterprise components are introduced, governance of the Apache-2.0 repository and ownership of separate commercial components should remain clearly documented. Open-source contributions must not be silently moved behind a proprietary license.
