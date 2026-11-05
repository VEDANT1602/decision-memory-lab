# Data card and trust boundaries

All data was authored for this independent portfolio experiment. The two tenants, release versions, approvals, routes, and operational notes are fictional. MIT applies to the original code and fixtures.

`scripts/generate_data.py` generates 35 facts, 35 source files, and 14 contract cases. There is no training/test distribution or learned model. Cases deliberately exercise known boundaries and should not be interpreted as a statistical estimate of real task success.

The `changed-new` source is intentionally inconsistent with its recorded digest. This is the source-edit fixture; do not "repair" its manifest during reproduction. Other digests should match. Competing region records intentionally have no supersession relation.

Times are nonnegative fictional observation units. A record observed at the query time is visible; expiry at the query time is expired. Queries before a correction see only records observed by that time, but source checks still use the run's current loaded snapshots. This conservative behavior is not a historical source archive.

The whole ledger and all files are validated at load. Missing or malformed input aborts the load instead of creating an apparently complete partial scan. The source path must resolve within the data root, including symlink resolution. Use only a local dataset directory controlled by the host; this is not a hardened sandbox against concurrent filesystem mutation.

Principal objects are trusted host inputs. A memory value, tenant label, or search term cannot create a principal. There is no web authentication layer in this repository. The dataset owner can edit both a record and its digest, so digest matching is integrity checking relative to a supplied manifest, not an authenticity proof or verification that a fact's value is entailed by the source. The public in-memory record dictionaries remain mutable; the trusted host must not mutate a loaded ledger while using it. Immutability is a caller discipline in this prototype.

Memory text remains untrusted even if marked reviewed. The fixture containing imperative text tests preservation as JSON data, not resistance by any downstream model. Downstream tools must enforce their own authorization independently.
