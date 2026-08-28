# Desktop services

Future services are deliberately separated by authority:

- unprivileged session supervision;
- individual typed capability services;
- controlled network egress/resolution;
- minimal privileged update/rollback service.

No single runtime service may combine webpage input, arbitrary capability
issuance, image generation, and update-signing authority.
