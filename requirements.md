# ALMG requirements

ALMG provides one dynamic workbench for designing, generating, testing, and
exporting custom models. The user describes the desired outcome in chat.
Local Qwen gathers missing details and selects registered training,
evaluation, simulation, and export tools at runtime as the task requires.
ALMG executes the approved plan and presents progress, results, and evidence
in the same work pane across model types.

ALMG is a Flutter desktop app with a local Python backend. Its goal is to turn a plain-language request into a dataset, a trained model, and an evaluation report. The current release target is Apple silicon macOS. The initial GitHub commit includes local Qwen chat and text-classifier training. [GitHub repository](https://github.com/arpit-it/ALMG)

## P0 · Validate the first macOS release

- [x] Publish a stable versioned release with the release workflow and verify that GitHub Releases contains the app ZIP and SHA-256 checksum. Download the ZIP, verify the checksum, and confirm that it contains the app and backend source. Keep model weights, chat databases, training output, and credentials out of Git and release assets.
  Local verification: a ZIP assembled with the workflow’s packaging commands
  passed SHA-256 verification and contained the app and backend source. The
  ARM64-only build was confirmed with `lipo`, and the app opened to the
  Dashboard after extraction from the verified ZIP. The published main-branch prerelease
  `v1.0.0-main.1` contained the ZIP and checksum. The downloaded ZIP passed
  SHA-256 verification, contained the backend source and ARM64 app, and opened
  to Chat on the existing Mac installation. The published main-branch
  prerelease `v1.0.0-main.3` also passed the downloaded SHA-256 check,
  contained the ARM64 app and backend source, and opened to the Dashboard
  on that Mac. GitHub Actions run [43714250108](https://github.com/arpit-it/ALMG/actions/runs/43714250108)
  completed successfully after a push to `main` and published this prerelease.
  A local ARM64 package built with an explicit backend file list passed its
  SHA-256 check, contained exactly the eight expected backend files, and
  opened to the Dashboard after extraction.
  The workflow now stages each ZIP in a fresh directory. A local ARM64
  packaging run ignored a stale training output fixture in the old staging
  directory. The ZIP passed its checksum, contained all eight backend files,
  and the extracted app opened to the Dashboard.
  The packaging step now tests ZIP integrity before writing its checksum.
  The check rejected a truncated local fixture. A fresh package passed
  both checks and the extracted ARM64 app opened to the Dashboard.
  The publish step now requires the checksum to name the release ZIP.
  With a local tag fixture and a stub publisher, a checksum for an unrelated
  file stopped publication. The correct checksum passed and the ZIP opened
  to the Dashboard after extraction.
  Pull request runs now execute the ARM64 build and packaging checks.
  The same workflow commands built the app locally from the current source,
  produced a ZIP that passed integrity and SHA-256 verification, and the
  extracted app opened to the Dashboard.
  Packaging now checks that the app bundle version matches the resolved
  release version. A local version mismatch stopped packaging. With the
  matching version, the ZIP passed SHA-256 verification and the extracted
  app opened to the Dashboard.
  Packaging now refreshes and verifies the local ad hoc signatures.
  A fixture with an invalid nested signature passed strict verification
  after packaging and extraction. Its ZIP passed SHA-256 verification and
  the extracted app opened to the Dashboard.
  The workflow now checks the signature again on the app extracted from
  the final ZIP. That check and the checksum passed locally, and the app
  from the same archive opened to the Dashboard.
  The workflow also compares the extracted backend directory with the
  staged source. The directories matched in a local package run, the ZIP
  passed SHA-256 verification, and the extracted app opened to the Dashboard.
  Release assets now include the full release tag. The local `v1.0.1`
  fixture produced `ALMG-v1.0.1-macOS-arm64.zip` and its matching SHA-256
  file. The checksum passed, the extracted app launched, and a stub publisher
  received both filenames. A checksum naming another file was rejected.
  GitHub Actions can also publish a stable release from an on-demand run
  on main, without a tag push. A local fixture with stable tags up to
  `v1.0.10` and a newer prerelease selected `v1.0.11`. The built ZIP used
  that tag in its filename, passed its checksum, and the extracted macOS
  app launched. A stub publisher received the stable tag and matching assets.
  GitHub Actions [run 43860091807](https://github.com/arpit-it/ALMG/actions/runs/43860091807)
  published stable [`v1.0.0`](https://github.com/arpit-it/ALMG/releases/tag/v1.0.0)
  from main. The downloaded versioned ZIP matched the published SHA-256,
  contained the eight expected backend source and setup files, and passed
  strict signature verification. The extracted ARM64 app launched on this Mac.
- [x] Test a fresh installation on an Apple silicon Mac. Follow the documented Python setup, register the backend, download and verify the checkpoint, send a chat message, and confirm that history survives a relaunch.
  The isolated Mac build reached Chat with setup required and showed a live
  transfer rate of 24.8 MB/s beside checkpoint progress in Settings. In a fresh
  Python environment with a separate macOS service, port, model directory,
  and chat database, ALMG downloaded and verified the 16.07 GB checkpoint.
  Qwen answered `42` in Chat, and the prompt and reply were both visible
  after quitting, relaunching, and reopening the conversation.
- [x] Document signing and notarization requirements for public distribution. Verify the downloaded app opens on the available Apple silicon Mac.
  The README documents Developer ID signing and Apple notarization. The
  downloaded `v1.0.0` ZIP matched its published SHA-256, and the extracted
  app launched on the existing Mac. This launch was accepted in place of
  a separate clean Mac test. The release uses ad hoc signing, and first
  launch under Gatekeeper on a clean Mac remains untested.
- [x] Add automated checks for pull requests. Run Flutter analysis, widget tests, and offline Python tests. Cover the macOS stop and restart flow, interrupted replies, attachment persistence, and checkpoint download recovery.
  Verified in isolated macOS Settings: Stop runtime showed Runtime stopped,
  and Restart backend restored Connected and Verified and ready to use.
  Offline tests now cover acknowledgment before shutdown and rejection of
  stop requests for manually started backends. A socket fixture verifies that
  the replacement backend accepts a connection queued on its inherited
  listener. Flutter tests cover Settings retries until connection and stopping
  when the retry window is exhausted. The rebuilt isolated Mac app again
  showed Runtime stopped, then Connected with the verified model. An offline
  checkpoint test covers resuming a partial file
  after restart and verifying its checksum. In the isolated Mac app, Settings
  resumed the local fixture and reported Verified and ready to use. The Mac
  chat showed the interruption and restored the prompt after a fixture emitted
  a delta and failed. An offline stream test confirms no failed turn is saved.
  In a fail-once fixture in Mac Chat, resending the restored draft produced
  one saved prompt and one reply. The offline stream test now also checks
  that retrying with the same message token saves exactly one turn. Offline
  tests cover attachment persistence, and the isolated Mac app showed the
  attached filename and Qwen’s correct fixture code after relaunch. The pull
  request workflow runs Flutter analysis, Flutter tests, and the offline
  Python suite. All three checks passed locally.

## P1 · Make text-classifier training reliable

- [x] Let users review and edit labels, dataset requirements, success metrics, and any web queries before training. Require approval before sending queries or fetching source pages, and store approved queries and source URLs with the dataset.
  Verified in the Mac app: saving an edited query updates the visible proposal
  and leaves search awaiting separate approval. In the rebuilt Mac app, replacing
  a proposed classifier label updated the plan while dataset approval remained
  pending. In the isolated Mac build, changing the proposed macro F1 target
  to 0.92 left dataset approval pending. The isolated Mac app also saved a
  change from 40 to 25 local examples per label without approving generation.
  An offline fixture produced 25 examples for each of two labels. The isolated
  Mac app released a web classifier fixture after inference preview. Its export
  contained the approved queries and source URLs, with each row linked to its
  query. The isolated Mac app hid web approval for an empty query list,
  and the backend rejected an empty approval. Offline tests confirm that
  empty and stale approvals leave the job pending and start no worker.
  In the isolated Mac app, approving the displayed fixture query populated
  the dataset preview and left training awaiting separate approval. This test
  used a local search response. The rebuilt Mac app showed the exact query,
  Brave Search as the destination, and how ALMG uses excerpts and records
  source URLs before approval. In the isolated Mac app, approving a search
  without a Brave API key showed the configuration error and kept dataset
  approval pending, with local generation and CSV import still available.
  An offline search failure returned the Mac app to dataset approval with
  the query, error, and local dataset choices visible. An empty offline search
  response also returned to dataset approval and offered query edits and local
  dataset choices. After a backend restart, the isolated Mac app reopened
  an interrupted collection fixture with the original query and required
  fresh approval before retrying. A local collection fixture with billing
  examples only returned to dataset approval and identified shipping as the
  missing class. With an approved offline search fixture, the rebuilt Mac
  app showed the approved query and each example’s source URL before separate
  training approval. In a local search response, two excerpts with the same
  retained text yielded one billing example, while a distinct shipping
  excerpt and both retained source URLs appeared in the Mac preview.
  A mixed offline response skipped malformed entries and showed both valid
  examples and URLs in the Mac app before separate training approval.
  A Mac web fixture preserved both original URLs in the preview while the
  saved dataset grouped hostname variants with different ports together.
  Editing the query after an empty result cleared the previous error in the
  isolated Mac app and required fresh approval. In the rebuilt Mac app,
  typing immediately after opening the query editor updated its first field
  without a click and saving kept approval pending. Clearing the last query
  in the rebuilt Mac app removed web approval and left local generation and
  CSV import available. The rebuilt Mac app also accepted a new query on
  that empty proposal and showed it with web approval still pending.
  Saving the same query twice in the isolated Mac app showed a validation
  message and kept the original proposal pending approval.
  Approving a saved Mac fixture with three entries and two distinct queries
  recorded two search steps and previewed one result from each query.
  Saving the label editor in the isolated Mac app cleared the fixture's
  previous dataset error and left dataset approval pending.
  In the rebuilt Mac app, approving two English Wikipedia queries against a
  local fixture produced two labeled preview rows with their approved queries
  and source URLs. Training remained pending.
  In the Mac app, approving two queries returned 40 live English Wikipedia
  excerpts. A local labeling fixture assigned 20 rows per class. Every saved
  row recorded its approved query and source URL. The app showed the dataset
  preview and waited for separate training approval.

  The rebuilt Mac app showed English Wikipedia (en.wikipedia.org) for classifier
  queries and Wikimedia Commons (commons.wikimedia.org) for image queries before
  approval in local fixtures. Provider selection, custom sites, and page approval
  for text collection remain open.
  Clearing both fixture queries in the rebuilt Mac app hid the Wikipedia
  disclosure and web approval while leaving local generation and CSV import.
  In the rebuilt Mac app, approving two fixture queries displayed two source
  URLs for review. A second approval prepared two excerpts with query and URL
  provenance and left training pending. Fetching full pages remains open.
  Removing a query from source review in the rebuilt Mac app discarded the
  displayed sources and returned the remaining query to approval.
  The rebuilt Mac app showed the fixture excerpt, approved query, and source
  URL together before excerpt approval.
  In the rebuilt Mac app, deselecting one of three fixture sources and
  approving the selection prepared only the other two excerpts.
  Clearing all three selections disabled excerpt approval in the rebuilt Mac
  app, and reselecting one source enabled approval again.
  The rebuilt Mac app exposed each of three fixture URLs as its checkbox
  label. Toggling the orchard fruit checkbox cleared only that selection.
  Approving a query in the Mac app against a local HTTP 302 fixture returned
  to dataset approval without following the redirect or showing results.
  The Mac app explained that Wikipedia redirected the approved search and
  offered a retry or a local dataset. The loopback fixture logged the original
  request and no request to the redirect destination.
  Approving a search against a local fixture returning HTTP 200 with a null
  page list restored dataset approval and displayed an invalid response message
  with retry and local dataset options.
  After approving two fixture queries in the Mac app, the source review showed
  one checkbox per URL, including when a page returned distinct excerpts.
  An approved search against a local HTTP 429 fixture returned the Mac app
  to dataset approval with an explanation and options to retry later or use
  a local dataset.
  In the Mac app, an approved search against a 21-result fixture showed the
  usable result at position 20 and excluded the result at position 21.
  A local HTTP 200 fixture with a non-JSON body returned the Mac app to
  dataset approval and displayed the invalid search response message.
  An approved search against a local HTTP 503 fixture returned the Mac app
  to dataset approval with a temporary outage message and a local option.
  With an unreachable loopback search endpoint, approving queries returned
  the Mac app to dataset approval with connection and local dataset options.
  In the rebuilt Mac app, the fixture plan displayed the Wikipedia host,
  20-result limit per query, and excerpt review step before search approval.
  Approving two fixture queries still opened source review after moving the
  pause between requests so it no longer delays review after the final query.
  A local search fixture one byte over the response size limit returned the
  Mac app to dataset approval with a download limit message.
  An interrupted local Wikipedia response returned the Mac app to dataset
  approval with retry and local dataset options. The provider catalog,
  custom websites, and full-page collection remain open.
  The rebuilt Mac app showed English Wikipedia for the classifier fixture
  and Wikimedia Commons for the image fixture, with the domain and
  result limit visible before search approval in both plans.
  Browsing providers in the rebuilt Mac app showed Wikipedia and Commons
  as available and the seven other starter sources as planned. Closing the
  catalog left the fixture at dataset approval. Provider selection, custom
  websites, and full-page collection still need implementation.
  In the rebuilt Mac app, removing all classifier fixture queries kept
  the catalog accessible and removed the web search approval button.
  The rebuilt Mac image fixture marked Wikimedia Commons as the current
  plan provider in the catalog and still awaited approval after closing it.
  The rebuilt Mac classifier displayed titles beside excerpts and source
  URLs after approved fixture searches. Results without titles remained
  available for review.
  After excerpt approval, the rebuilt Mac app showed the three fixture
  examples with their source URLs and queries, plus the two available
  article titles, in the dataset preview.
  Before approving a classifier fixture's queries in the rebuilt Mac app,
  the provider catalog showed en.wikipedia.org and commons.wikimedia.org
  and identified Wikipedia as the current plan. Provider selection, custom
  websites, and approved full-page retrieval remain open.
  The rebuilt Mac app named Wikipedia and Wikimedia Commons on their
  respective search approval buttons. Approving the local Wikipedia
  fixture opened source review with three candidates.
  Approving an empty Commons fixture search in the Mac app returned to
  dataset approval with an explanation and options to edit the query
  or use a local dataset.
  In the Mac app, a Commons discovery fixture returned HTTP 302 after
  search approval. ALMG did not contact the redirect target and returned
  to dataset approval with an explanation.
  A mixed Commons fixture in the Mac app showed the CC BY 4.0 image
  and its URL at download approval and omitted the result with no license.
  Approving an older saved Commons result without license information
  in the Mac app returned to dataset approval without starting a download.
  After approving a Commons fixture that returned 21 results, the Mac app
  showed candidate 20 immediately before the download approval button.
  A Commons fixture with repeated image URLs showed a single candidate
  at download approval in the Mac app.
  With a malformed Commons entry followed by a valid image, the Mac app
  opened download review and showed the valid candidate.
  A Commons fixture with null license metadata on one image also
  reached download review with the remaining valid image in the Mac app.
  After approving search and download for a local Commons fixture with
  unreadable image data, the Mac app returned to dataset approval with
  options to revise the search or use a local dataset.
  A Commons search fixture returning HTTP 429 displayed a rate limit
  message and restored the dataset approval controls in the Mac app.
  A non-JSON Commons fixture response showed an invalid response message
  and restored retry and local dataset controls in the Mac app.
  A Commons fixture that returned a JSON array in place of a search
  object also restored approval with the invalid response message.
  In the Mac app, a fixture that simulated an interrupted Commons
  response returned to dataset approval with retry and local dataset options.
  A simulated Commons connection failure displayed connection guidance
  and restored the approval controls in the Mac app.
  In the rebuilt Mac app, editing a Commons query from download review
  removed the previous candidates and returned the revised query to
  search approval.
  In the Mac app, an approved Commons retry cleared the previous search
  error while the fixture was running and opened image download review.
  With the shared direct HTTP opener wired into Commons downloads,
  the Mac app separately approved a local fixture search and download
  and previewed six images with their source URLs and licenses.
  A second Mac fixture run confirmed that all six saved image rows
  retained the approved Commons query.
  The rebuilt Mac app reopened that fixture dataset and displayed
  the approved query alongside the image source and license.
  A fresh Mac fixture search also showed the approved query alongside
  each Commons candidate's URL and license before download approval.
  The rebuilt Mac app showed six fixture downloads and the 8 MiB
  per-image limit on the approval button. Approval prepared six images.
  The rebuilt Mac app let me deselect one of six Commons candidates.
  Approving the five remaining downloads saved exactly those five URLs
  in the fixture dataset and left training awaiting approval.
  The rebuilt Mac app displayed the five-image minimum and kept four
  selected Commons results in review. Selecting a fifth let me approve
  the downloads and preview the fixture dataset.
  With only one eligible Commons image in a local fixture, the Mac app
  returned to search approval and offered a broader query or local data.
  After approving six fixture downloads in the Mac app, ALMG reported
  one interrupted image and showed the other five in the dataset preview.
  A second Mac fixture supplied fewer bytes than one image response
  declared. ALMG skipped it and previewed the other five images.
  A local Commons search response declared more bytes than it sent.
  The Mac app reported the interruption and restored dataset approval.
  When one of six approved Commons fixture images declared more than
  8 MiB, the Mac app reported the limit and previewed the other five.
  A Commons search fixture declared a response over the JSON size limit.
  The Mac app reported the limit and restored dataset approval.
  A Commons fixture with one malformed Unicode image title reached
  download review with the remaining five images in the Mac app.
  The Mac app showed three valid Wikipedia fixture URLs after query
  approval and omitted the page with a newline in its key.
  After Commons search approval in the Mac app, download review retained
  all six valid fixture URLs and omitted a seventh URL containing a newline.
  A Commons search approved in the Mac app kept six titled, licensed fixture
  images for review and omitted a seventh image with a blank file title.
  After Commons approval in the Mac app, download review kept six fixture
  URLs and excluded the seventh because it contained a URL fragment.
  Approving a saved Commons review containing a fragment URL in the Mac
  app cleared the review and prompted a new search before downloading.
  The Mac app returned a saved Commons review with a blank file title to
  search approval before starting any downloads.
  After Wikipedia search approval in the Mac app, source review showed
  three valid articles and excluded a short excerpt padded with spaces.
  The Mac app kept three valid Wikipedia sources after search approval
  and excluded the excerpt containing an embedded NUL.
  Wikipedia source review in the Mac app retained an article URL while
  omitting its title with an embedded NUL. The Astronomía title appeared.
  After Commons search approval, the Mac app kept six licensed fixture
  images and excluded the result whose license label contained a NUL.
  The Mac app cleared a saved Commons review with a NUL in a license
  label and returned to search approval before any downloads started.
  The Mac app rejected download approval for a saved Commons file title
  containing a NUL. A fresh approved search returned to image review.
  After Commons search approval in the Mac app, download review showed six
  files from seven results. Two results shared a file title and had different URLs.
  The Mac app returned a saved Commons review to search approval when
  two selected fixture images shared a file title. Downloads did not start.
  The standard Mac debug bundle was rebuilt in place against a loopback
  fixture. Approving Wikipedia discovery reached article review in that bundle.
  An empty Commons fixture search in the Mac app returned to approval
  and offered a broader query or a local dataset.
  After approving fixture searches in the Mac app, source review reported
  three Wikipedia excerpts and six Commons images in their respective runs.
  An empty Wikipedia fixture search in the Mac app returned to approval
  with options to broaden the queries or use a local dataset.
  The Mac app showed three valid Wikipedia sources and omitted a fixture
  result whose page identifier had leading and trailing spaces.
  A Commons fixture with an unexpected response structure returned the Mac
  app to approval with an invalid response message and a retry option.
  The Mac app returned to approval when a Wikipedia fixture sent an error
  alongside article results. It displayed a retry or local dataset option.
  Approved Wikipedia and Commons fixture searches returning HTTP 403
  displayed the provider, status code, and recovery options in the Mac app.
  The Mac app logged the download host and count after approving six
  Commons fixture images. The resulting dataset preview showed six examples.
  Approving three Wikipedia fixture excerpts in the Mac app recorded
  the selection count in Activity history and previewed three examples.
  The Mac app reopened saved interrupted Wikipedia and Commons searches
  at approval. Fresh consent reached review with three excerpts and six images.
  The Mac app reopened an interrupted Commons download fixture at image
  review. Fresh download approval produced a preview with six examples.
  The Mac app reopened interrupted Wikipedia dataset preparation at
  excerpt review. Fresh approval produced a preview with three examples.
  In the Mac app, two failed Commons fixture downloads returned to the
  saved image review. Approving the same six URLs again built six examples.
  A fixture labeling failure in the Mac app returned to Wikipedia excerpt
  review. Renewed approval produced a preview with the three saved excerpts.
  Wikipedia review in the rebuilt Mac app explained that excerpt approval
  labels selected text locally. Approving three fixture excerpts previewed
  three examples. Full article retrieval remains open.
  Commons download review showed the host and a 48 MiB cap for six
  fixture images. Deselecting one lowered the cap to 40 MiB. Approval
  produced five examples in the rebuilt Mac app.
  The rebuilt Mac app showed a cap of 20 results per Wikipedia query and
  40 total for two fixture queries. Approval returned three excerpts.
  The rebuilt Mac app used limits supplied by the backend on both approval
  screens. Fixtures advertised four results per Wikipedia query and five
  Commons results. Both approved searches reached source review.
  The rebuilt Mac app sent the displayed result limit with search approval.
  A Commons fixture changed its limit from five to six. The first approval
  returned to review and the second produced six candidates.
  A Commons fixture changed its download limit from 8 to 7 MiB per image.
  The rebuilt Mac app refreshed review to 42 MiB for six images and
  required another approval before producing the six-example dataset.
  Wikipedia source review in the rebuilt Mac app cleared all three fixture
  selections and restored them with Select all. Approval previewed three examples.
  Commons image review in the rebuilt Mac app cleared the six fixture
  selections and restored them with Select all. Approval previewed six examples.
  Commons image review exposed each checkbox with its source URL in the
  rebuilt Mac app. Deselecting a labeled URL excluded it from the five
  examples produced after download approval.
  Project settings in the rebuilt Mac app saved an HTTPS discovery website
  and displayed it when reopened. This saves one URL per project. Website
  discovery, access and reuse checks, and page collection remain open.
  The discovery catalog in the rebuilt Mac app displayed the saved fixture
  website with discovery unavailable. Closing the catalog left Wikipedia
  search awaiting approval. Website crawling remains open.
  The rebuilt Mac catalog showed the fixture URL in its own Project website
  section and displayed its discovery availability.
  The rebuilt Mac app opened project settings from the discovery catalog.
  Saving a replacement fixture URL and reopening the catalog showed the
  updated URL. Website crawling and collection remain open.
  Clearing the fixture website in the rebuilt Mac app and saving settings
  removed its entry from the discovery catalog.
  In the rebuilt Mac app, project settings rejected a numeric IP and
  saved an HTTPS domain URL that appeared in the discovery catalog.
  Website access checks and crawling remain open.
  Saving an uppercase HTTPS scheme and host with port 443 in the Mac app
  displayed a lowercase host without the default port and preserved the path.
  In the rebuilt Mac app, project settings rejected an incomplete URL
  escape and displayed the corrected escaped path in the discovery catalog.
  The rebuilt Mac app encoded brackets in a saved website path and kept
  an existing space escape intact. A backend fixture verified UTF-8 encoding.
  Resaving a fixture with an internationalized domain in the Mac app
  displayed the equivalent ASCII hostname and preserved the path.
  On the rebuilt Mac app, an instructions-only save preserved a legacy website
  URL in a local fixture project while persisting the new instructions.
  After saving a replacement fixture website, the rebuilt Mac app returned
  directly to the discovery catalog and displayed the saved URL.
  The rebuilt Mac app showed the HTTPS URL format before editing, then
  saved a matching fixture address and displayed it in the discovery catalog.
  The rebuilt Mac app kept settings open after rejecting a fixture HTTP
  address and displayed the HTTPS requirement in plain language.
  Closing a draft website edit in the rebuilt Mac app returned to the
  catalog without reloading the project. Saving refreshed the displayed URL.
  The rebuilt Mac app rejected a fixture hostname longer than 253
  characters even though each DNS label fit its own length limit.
  Clearing a fixture website in the rebuilt Mac app showed No website
  added in the catalog. Add project website opened the empty editor.
  In the rebuilt Mac app, the catalog opened from both fixture source
  reviews, showed the current provider, and returned to the candidate list.
  The rebuilt Mac app opened a saved Wikipedia fixture without query
  metadata and showed its excerpt, source URL, and approval control.
  After approved Commons fixture search, the rebuilt Mac app displayed
  source and license review guidance beside the image download decision.
  The rebuilt Mac app showed selectable Commons file page URLs beside
  each fixture image download URL and license after search approval.
  After approving six Commons fixture downloads in the rebuilt Mac app,
  the dataset preview showed file pages alongside download URLs and licenses.
  After Commons search approval, the rebuilt Mac app showed six of seven
  fixture results, omitting the duplicate title spelled with an underscore.
  In the rebuilt Mac app, an approved Commons fixture search kept six
  results and omitted a duplicate with a canonically equivalent Unicode title.
  After Wikipedia fixture search approval, the rebuilt Mac app showed
  three sources and omitted the alternate spelling of the same page key.
  The rebuilt Mac app approved two saved Wikipedia fixture excerpts
  without query metadata and displayed both article titles and source URLs
  in the dataset preview.
  The rebuilt Mac app rejected an encoded NUL in a fixture website path
  and saved the corrected path with an encoded space intact.
  The rebuilt Mac app rejected a bracketed IPvFuture fixture address
  and kept the website editor open with a domain name validation message.
  The rebuilt Mac app rejected a fixture URL with an empty port and
  kept the project website editor open for correction.
  The rebuilt Mac app reached review for both fixture providers with
  explicit result limits required. A regression test verified that omitting
  the limit leaves search awaiting approval and starts no worker.
  With explicit download limits required, the rebuilt Mac app approved
  six Commons fixture downloads at 8 MiB each and reached dataset preview.
  After Commons fixture search approval, the rebuilt Mac app showed
  the source and license guidance above the six candidates.
  An approved Wikipedia fixture search in the rebuilt Mac app showed four
  distinct excerpts, omitting the duplicate with equivalent Unicode text.
  In the rebuilt Mac app, approving two offline Wikipedia fixture queries
  showed three distinct excerpts for review. The alternate
  `orchard__fruit` title with different excerpt text was excluded;
  `orchard_fruit` and both unrelated articles remained. Broader provider
  and page collection verification remains open.
  After offline Wikipedia search approval in the macOS app, source review
  showed all three valid fixture articles and omitted an excerpt with a
  control character beyond the 450-character preview limit.
  In the rebuilt Mac app, approving three offline Wikipedia excerpts
  reached dataset preview with two fruit examples and one astronomy example
  even though the fixture label response included a malformed row.
  In the rebuilt Mac app, the Commons fixture catalog showed Wikimedia
  Commons as the current plan and all seven planned providers with their
  domains and an explicit unavailable notice. Those adapters remain open.
  In the Mac app, saving the unchanged Commons fixture query kept six
  results in review and preserved one unchecked result. Changing the query
  cleared the review and required fresh search approval.
  In the rebuilt Mac app, changing the Commons fixture query to
  "landscape photos" displayed the revised query and a message to approve
  a new search. The six old results were removed from review.
  After approving three offline Wikipedia excerpts in the rebuilt Mac app,
  the dataset preview named English Wikipedia beside each article URL and
  retained the approved query. New dataset rows also carry the provider ID.
  In the rebuilt Mac app, approving six offline Commons images reached
  dataset preview with Wikimedia Commons beside the source URLs and the
  license and approved query. All six saved rows carry the Commons provider ID.
  The rebuilt Mac app reopened the six saved Commons fixture examples and
  displayed source attribution from provider IDs. URL fallback remains for
  older rows. Additional provider adapters and full page collection are open.
  The rebuilt Mac app disclosed the Library of Congress destination, first
  query and 20-record limit before approval. The offline fixture showed one
  catalog title and URL, excluded a restricted item, and returned to dataset
  approval without collecting records. Reuse checks, page collection and
  other provider adapters remain open.
  An approved offline Library of Congress search with zero results
  returned to dataset approval and offered query editing or another source.
  After approving an offline Library of Congress search, the rebuilt Mac
  app showed the approved query above the matching catalog title and URL.
  The Mac app returned to dataset approval after an offline Library of
  Congress HTTP 429 response and offered waiting or choosing another source.
  The fixture test observed one request per approval.
  After approving an offline catalog search in the rebuilt Mac app, an
  item with a legacy HTTP identifier appeared in review with its HTTPS URL.
  In the rebuilt Mac app, an offline catalog result disclosed its item
  metadata URL before a separate approval loaded rights and access
  advisories. Review showed the permission-required statement alongside
  public-viewing access. Reuse approval and dataset collection remain open.
  In the rebuilt Mac app, a second approved item request with malformed
  rights metadata removed the earlier advisories and showed retry guidance
  with reuse rights still unverified.
  The rebuilt Mac app reopened an interrupted item metadata fixture at
  catalog review, retained its title and URL, cleared earlier advisories,
  and loaded fresh statements only after item URL approval.
  The rebuilt Mac app recorded explicit reuse permission with a written
  basis for a local fixture item after advisory review. Refreshing metadata
  removed that approval and required review again. Dataset collection and
  remaining provider adapters are still open.
  In the rebuilt Mac app, a fixture with two previously reuse-approved
  catalog descriptions required collection approval before local labeling.
  Dataset preview showed fruit and astronomy examples with catalog URLs
  and the approved query. Both saved rows retained the permission basis
  and advisories. Full document collection and other providers remain open.
  After offline catalog search approval, the rebuilt Mac app retained a
  newspaper issue URL with date and edition path segments in source review.
  Parser tests rejected literal and encoded parent-directory segments.
  Verified partial provider delivery (2026-11-18): after explicit collection
  approval in the rebuilt local Mac app, two offline catalog descriptions
  reached dataset preview with catalog record titles, source URLs, query,
  and recorded user reuse permission beside each example. The backend
  preview retains permission and advisory evidence. All 40 Python tests
  passed; Flutter analysis found no issues. Full document collection
  and remaining providers stay open under key-free web discovery.
  The rebuilt Mac app also explained the 40-character collection minimum
  for an empty and a short offline catalog description. Neither exposed
  collection approval; returning to dataset approval restored the source
  choices. All four Flutter tests passed. Provider delivery remains partial.
  Catalog review now allows per-record selection after permission review.
  In the rebuilt Mac app, deselecting one of three offline records changed
  approval to two selected; dataset preview and saved dataset contained
  exactly those two URLs. Five Flutter tests passed, including rejection
  of unreviewed, unapproved and short records; analysis found no issues.
  Full document collection and remaining providers are still open.
  Library of Congress discovery now requires approval of the full displayed
  query list, 20 records per query and 40 total. In the rebuilt Mac app,
  approving orchard and astronomy fixture queries produced both records
  with the matching query beside each URL; the fixture logged exactly
  those two searches. Tests verify cross-query URL deduplication and
  stopping contacts at the total limit. All 42 Python tests passed and
  Flutter analysis passed. The overall provider requirement remains open.
  Item advisory loading now checks the returned catalog ID against the
  approved source URL, accepting the equivalent legacy HTTP identifier.
  In the rebuilt Mac app, a different-item fixture showed retry guidance
  without advisories or reuse approval; a separately approved matching-ID
  retry displayed the advisories and reuse review. All 44 Python tests
  passed, including missing, mismatched and deceptive-host identities
  and clearing earlier permission on mismatch. Provider scope stays open.
  Item review also requires metadata to explicitly report unrestricted
  access. The rebuilt Mac app blocked a restricted offline item with
  specific recovery guidance and no reuse approval; a separately approved
  unrestricted retry restored advisory review. All 46 Python tests passed,
  including unknown/malformed access values and removal of earlier
  permission and description after a restricted refresh. Remaining
  providers and full document collection are still open.
  Europe PMC now offers a consent-gated publication metadata preview for
  text classification. The rebuilt Mac app disclosed www.ebi.ac.uk, the
  first query and 20-record limit before approval. An offline fixture then
  displayed two supported publication titles, Europe PMC URLs and their
  approved query, omitted a malformed ID, and returned to dataset approval.
  Reuse stays unverified; abstract/full-text collection and other provider
  work remain open. All 49 Python tests and Flutter analysis passed.
  Europe PMC abstract metadata now requires separate approval of a listed
  publication URL. The rebuilt Mac app loaded an offline abstract only
  for the approved record, displayed normalized text, and kept reuse
  unverified. Fixture logs showed one discovery request and one exact-ID
  core metadata request; no publication link was fetched. All 52 Python
  tests and Flutter analysis passed. Tests cover mismatched identities,
  missing/invalid text and stale-text removal on refresh failure. Rights
  review, dataset collection and full-text loading remain open.
  Interrupted Europe PMC abstract loading now restores the publication
  list for reapproval instead of discarding discovery results. The
  relaunched Mac app retained an offline title and URL, showed interruption
  guidance without stale abstract text, then loaded the abstract only
  after fresh approval. All 53 Python tests passed; the persistence test
  confirms restored state is saved without a network request. Rights
  review, dataset collection and remaining provider work stay open.
  Europe PMC abstract review now records explicit user reuse permission
  with the publication URL and reviewed abstract SHA-256. The rebuilt
  Mac app accepted a local fixture permission basis and displayed its
  evidence; approving an abstract refresh removed that permission and
  required a new decision. All 55 Python tests and Flutter analysis
  passed. Tests reject missing review, unmatched URL and unconfirmed or
  short permission decisions. Dataset collection, full-text loading and
  remaining provider implementation are still open.
  Selected, reuse-approved Europe PMC abstracts can now enter classifier
  datasets after separate collection approval. In the rebuilt Mac app,
  deselecting one of three offline abstracts changed approval to two;
  dataset preview and saved rows contained exactly those two URLs, with
  titles, queries and permission evidence. Collection verifies the current
  abstract checksum against its permission record. All 56 Python tests
  and Flutter analysis passed. Full-text loading and other starter
  providers remain open, so the overall requirement stays incomplete.
  Europe PMC discovery now requires approval of all displayed queries,
  20 results per query and 40 total. The rebuilt Mac app disclosed both
  offline queries and returned orchard and astronomy publications with
  matching query provenance; a shared publication appeared only once.
  All 58 Python tests and Flutter analysis passed. Tests verify URL
  deduplication and no further provider contacts after the total limit.
  Full-text loading and other starter providers remain open.
  Wikidata now provides a consent-gated English item search preview.
  In the rebuilt Mac app, approval disclosed www.wikidata.org, both
  queries, 20 items per query and 40 total. Offline source review showed
  two entity labels, Q IDs, descriptions, validated URLs and matching
  queries; a malformed ID was omitted and return navigation worked.
  All 62 Python tests and Flutter analysis passed, including API scope,
  deduplication and contact-limit checks. Entity dataset collection and
  the remaining providers stay open.
  Wikidata review now discloses structured-data terms with their source
  URL and records explicit per-entity reuse permission. In the rebuilt
  Mac app, approving one offline entity displayed its permission basis
  while the second stayed unapproved. Saved evidence matched the label
  and description SHA-256 and retained the terms source. All 63 Python
  tests and Flutter analysis passed. Entity dataset collection and
  remaining provider work are still open.
  Selected, reuse-approved Wikidata labels and descriptions can now form
  classifier examples after collection approval. The rebuilt Mac app
  deselected one of three offline entities and prepared exactly the two
  selected URLs. Preview and saved rows retained query and permission
  evidence, including terms source and reviewed-text checksum. All 64
  Python tests and Flutter analysis passed; changed text and invalid URL
  selections are rejected. Entity tagging, graph training and remaining
  providers stay open; the overall requirement is not complete.
  World Bank now offers an approval-gated first-page indicator catalog
  preview. The rebuilt Mac app disclosed api.worldbank.org, the 20-record
  limit and unfiltered catalog scope before loading an offline fixture.
  Review showed two valid indicators with notes, organizations, source
  IDs and source-specific metadata URLs; malformed codes were omitted
  and return navigation worked. All 67 Python tests and Flutter analysis
  passed. Query-based indicator discovery, reuse review, observations
  and dataset collection remain open.
  World Bank catalog paging now needs separate approval for each next
  page. The rebuilt Mac app disclosed page 2 and its 20-record limit,
  loaded the offline second page only after approval, and showed page 2
  of 2 without another next-page action. Fixture logs contained only the
  two approved catalog requests. All 69 Python tests and Flutter analysis
  passed, including mismatched-page rejection and retaining the prior
  preview after loading failure. Query matching, reuse review and
  observation/dataset collection are still open.
  Loaded World Bank catalog pages can now be filtered locally across
  codes, names, notes, source names and organizations. In the rebuilt
  Mac app, a case-insensitive fixture filter reduced two records to one,
  clearing restored both, and an unmatched filter showed recovery
  guidance. Fixture logs showed no extra provider calls. All six Flutter
  tests and analysis passed. Filtering covers only the loaded page;
  provider-side query discovery, reuse and observation collection stay open.
  World Bank catalog descriptions now support explicit per-indicator
  reuse decisions, with a terms reference and metadata-only scope shown
  in the dialog. The rebuilt Mac app recorded separate offline permission
  bases for two indicators and retained the first across app relaunch.
  Saved evidence included the metadata scope and a checksum covering the
  description and source context. All 70 Python tests and Flutter analysis
  passed; observation-scope decisions are rejected. Dataset/observation
  collection and provider-side query discovery remain open.
  Selected, reuse-approved World Bank catalog descriptions can now enter
  classifier datasets after separate collection approval. In the rebuilt
  Mac app, deselecting one of three offline descriptions prepared exactly
  two examples. Preview and saved rows retained metadata-only scope,
  source organization, source URL and permission checksum. All 71 Python
  tests and Flutter analysis passed; changed source context and
  observation-scoped permission are rejected. Country/year observations,
  provider-side query discovery and the remaining providers stay open.
  Federal Register now provides consent-gated document metadata discovery.
  The rebuilt Mac app disclosed the destination, both queries and limits
  before an offline search, then showed two titles, document numbers,
  validated URLs and matching queries. A malformed URL was omitted and
  return navigation worked. All 75 Python tests and Flutter analysis
  passed, including metadata-only field requests, URL identity checks,
  deduplication and contact limits. Reuse review, content collection and
  the remaining provider work stay open.
  Federal Register summary metadata now requires separate approval of a
  listed document URL. The rebuilt Mac app loaded the offline summary
  only for the approved document; the second remained unloaded. Fixture
  logs showed one exact-document summary request after approval. All 77
  Python tests and Flutter analysis passed, including response identity,
  summary size/text validation and stale-text removal after failure.
  Reuse review, dataset collection and full-text loading remain open.
  Federal Register summaries now support explicit reuse permission tied
  to the reviewed title and summary checksum. The rebuilt Mac app showed
  summary-only scope in the decision dialog, recorded an offline
  permission basis, and cleared it after an approved summary refresh.
  All 79 Python tests and Flutter analysis passed, including scope,
  confirmation and matching-URL checks. Dataset collection, full-text
  loading and remaining provider work stay open.
  Selected, reuse-approved Federal Register summaries can now enter
  classifier datasets after collection approval. The rebuilt Mac app
  deselected one of three offline summaries and prepared exactly the
  two selected documents. Preview and saved rows retained document
  numbers, source URLs, queries, summary scope and matching permission
  checksums. All 80 Python tests and Flutter analysis passed. Full-text
  loading and the remaining providers remain open, so the overall
  discovery requirement is not complete.
  Crossref now provides consent-gated bibliographic metadata discovery.
  The rebuilt Mac app disclosed api.crossref.org, both queries and
  20-per-query/40-total limits before an offline search. Review showed
  titles, publishers, types, DOI URLs and matching queries; malformed
  records were omitted and return navigation worked. All 84 Python tests
  and Flutter analysis passed, including metadata-only fields, DOI
  validation, deduplication and contact limits. Abstract collection,
  publisher-page reuse and SEC EDGAR remain open.
  Crossref abstract and license metadata now require separate approval
  of a listed DOI URL. In the rebuilt Mac app, only the approved offline
  abstract and supplied license statement appeared; reuse stayed
  unverified and the other DOI remained unloaded. Fixture logs showed
  one API work request without following DOI, publisher or license URLs.
  All 87 Python tests and Flutter analysis passed, including identity,
  license-link validation and stale-review removal. Abstract reuse,
  dataset collection, publisher pages and SEC EDGAR remain open.

  Crossref abstract reuse now requires an explicit abstract-only decision
  and permission basis, bound to the reviewed text, publisher and supplied
  license metadata checksum. In the rebuilt Mac app using local fixtures,
  the recorded basis appeared only for the reviewed DOI; refreshing its
  metadata removed the approval and restored the permission control. All
  89 Python tests and Flutter analysis passed. Dataset collection,
  publisher pages and SEC EDGAR remain open.

  Selected Crossref abstracts with current abstract-scoped permission can
  now enter text classification datasets. Local Mac app fixtures reached
  a two-example preview with DOI URLs, permission bases and abstract scope;
  deselection changed the approval count to zero. The final rebuilt app
  reopened that preview and displayed the insufficient-class-count warning.
  All 90 Python tests and Flutter analysis passed, including stale-license,
  changed-text and invalid-selection rejection. Publisher-page collection,
  SEC EDGAR and project website discovery remain open.

  Crossref review now explains why a nonempty abstract below the
  40-character collection minimum is unavailable, including after reuse
  permission is recorded. In the rebuilt Mac app, a short local fixture
  displayed the explanation before and after permission approval and
  exposed no collection control. Both Dart selection tests, all 10
  Crossref Python tests and Flutter analysis passed. The broader provider
  and project website discovery requirement remains open.

  SEC EDGAR now offers a CIK-based recent-filing metadata preview. The
  consent dialog shows the exact submissions endpoint and declared contact
  header; requests are serialized at at most one per second with no
  automatic retry. In the rebuilt Mac app, cancelling sent no fixture
  request; approval sent one and displayed the valid filing URL while
  omitting a malformed path. No filing contents or older submission files
  were loaded, and reuse stayed unverified. All 93 Python tests and Flutter
  analysis passed. Company lookup, filing reuse and content collection,
  project websites and other broad discovery criteria remain open.

  SEC company lookup now matches an entered name or ticker locally against
  the separately approved company association catalog, returning at most
  20 companies. In the rebuilt Mac app, a fixture lookup showed the matching
  company and omitted an invalid CIK; choosing it filled CIK 1234 and opened
  a separate submissions approval dialog. Logs confirmed one catalog
  request and no submissions request. All 94 Python tests and Flutter
  analysis passed. Filing reuse, content collection, project websites and
  the remaining broad discovery criteria stay open.

  SEC filing text preview now requires separate approval of a listed URL,
  contact header and 1 MiB limit. HTML/plain-text extraction displays at
  most 50,000 characters without linked-resource loading. In the rebuilt
  Mac app, cancelling left content unloaded; approval fetched only the
  listed local fixture and displayed its text without head or script text.
  Reuse stayed unverified and dataset collection unavailable. All 96 Python
  tests and Flutter analysis passed, including format/size limits, source
  validation and stale-preview removal. Filing reuse, dataset collection
  and project website discovery remain open.

  SEC filing previews now support an explicit preview-only reuse decision
  and permission basis, bound to filing identity, text and truncation status.
  In the rebuilt Mac app using local fixtures, the scope dialog and recorded
  basis appeared; an approved refresh removed the decision and restored the
  permission control. All 97 Python tests and Flutter analysis passed,
  including scope rejection, checksum changes and refresh invalidation.
  Dataset collection and project website discovery remain open.

  Selected SEC filing previews with current preview-scoped permission can
  now enter text classification datasets. In the rebuilt Mac app with
  local fixtures, deselecting one of three approved previews changed the
  count to two; collection showed exactly those two with SEC URLs, filing
  identity, preview scope and permission basis. Class-count warnings stayed
  visible and training was not started. All 98 Python tests and Flutter
  analysis passed, including stale-text, changed-truncation and invalid-
  selection rejection. Project website discovery and remaining broad
  provider criteria stay open.

  The built-in discovery provider dialog now lists SEC EDGAR as available
  instead of planned, with the company-lookup and submissions hosts and
  separate text/reuse approval requirements. The rebuilt Mac app displayed
  the updated entry from a local approval-stage fixture. Both existing
  navigation/layout widget tests passed. Project website crawling and
  remaining broad discovery criteria stay open.

  Saved project websites now offer a separately approved robots.txt review
  with an exact destination and 64 KiB limit. In the rebuilt Mac app using
  local fixtures, cancellation made no request; approval showed the robots
  guidance, and the final build reopened it with access and reuse still
  unverified. No pages were crawled. All 102 Python tests and Flutter
  analysis passed; targeted tests also passed after explicit multicast
  rejection was added. Network tests cover public-address pinning, TLS
  hostname preservation and bounded reads. Site access-rule approval,
  robots enforcement, crawling and per-page reuse review remain open.

  Project website access-rule review now records an explicit basis scoped
  to the saved website and displayed robots guidance checksum. In the
  rebuilt Mac app with local fixtures, the access-only dialog recorded the
  basis while reuse stayed unverified; a newly approved robots refresh
  removed the earlier decision and restored the review control. No crawl
  started. All 103 Python tests and Flutter analysis passed, including
  changed-site and scope rejection. Robots enforcement, crawling and
  per-page reuse approval remain open.

  Robots guidance now evaluates the saved website path for ALMG, combining
  specific groups with wildcard fallback, longest-rule precedence, Allow
  ties, wildcard/end anchors and encoded paths. In the rebuilt Mac app, an
  approved local fixture displayed disallowed and its matching /archive/
  rule; other-page checks and crawling remained unavailable. All 105 Python
  tests and Flutter analysis passed. Crawl-time robots enforcement,
  discovery crawling and per-page reuse approval remain open.

  Project websites now support separately approved one-page link discovery
  after current access-rule review and robots allowance. The request is
  bounded to 512 KiB and 20 allowed same-origin links, with a one-hour
  guidance lifetime and bounded crawl-delay handling. In the rebuilt Mac
  app, cancellation made no discovery request; approval of a local fixture
  showed exactly two allowed URLs and omitted disallowed/off-site links.
  No linked pages or resources were loaded and reuse stayed unverified.
  All 108 Python tests and Flutter analysis passed. Per-page fetching,
  content reuse review and dataset collection remain open.

  Discovered website URLs now require separate approval for a bounded HTML
  text preview. Current site access and per-URL robots rules are checked
  before the pinned request; previews retain at most 20,000 characters.
  In the rebuilt Mac app, cancellation made no page request, while approval
  loaded only the selected fixture, stripped head/script text and left the
  other URL unloaded. Reuse stayed unverified. All 110 Python tests and
  Flutter analysis passed, including stale-access/unsafe-URL rejection and
  failed-refresh cleanup. Content reuse review and dataset collection
  remain open.

  Website page previews now support explicit preview-only reuse permission
  with a recorded basis, bound to source, text, truncation and current
  access guidance. In the rebuilt Mac app using local fixtures, the scope
  dialog recorded the basis; an approved page refresh removed the decision
  and restored reuse review while the other URL stayed unloaded. All 111
  Python tests and Flutter analysis passed, including stale-guidance and
  invalid-scope rejection. Dataset collection and remaining broad
  discovery criteria stay open.

  Selected website page previews can now enter text classification datasets
  only while site access and per-preview reuse evidence remain current.
  In the rebuilt Mac app with local fixtures, deselecting one of three
  approved previews produced exactly the two selected examples with source
  URLs, discovery page, access-review basis and reuse basis. Class-count
  warnings remained visible; training was not started. All 112 Python
  tests, three Dart selection tests and Flutter analysis passed. The broad
  discovery requirement remains open pending verification of all criteria
  together, including provider settings and project website workflows.

  Projects now persist enabled discovery providers, with existing projects
  defaulting to the available set. The app labels disabled providers and
  blocks their searches; backend checks reject disabled discovery actions
  before workers start. In the rebuilt Mac app, disabling Crossref survived
  saving/reopening settings, showed Disabled in the provider list, and a
  search attempt showed the disabled message without a fixture request.
  All 113 Python tests and Flutter analysis passed, including project
  isolation, persistence, invalid-selection and disabled-request checks.
  Full cross-provider acceptance verification remains open.

  Discovery approval controls now visibly disable providers excluded by
  project settings and explain how to re-enable them. Disabled Commons
  also blocks downloads from existing search results. In the rebuilt Mac
  app, Crossref search was greyed out; enabling it in settings restored the
  control and an approved search reached local fixture results. All 114
  Python tests and Flutter analysis passed, including disabled Commons
  search/download rejection. Cross-provider acceptance verification stays
  open.

  Wikipedia excerpt collection now requires a recorded reuse basis for
  every selected result, bound to its displayed source, title and text.
  In the rebuilt Mac app with local fixtures, unreviewed excerpts were
  unavailable for selection; separate excerpt-only decisions enabled them,
  and collection showed two examples with sources, permission bases and
  search-excerpt scope. No full articles were fetched. All 115 Python tests
  and Flutter analysis passed, including stale-text, invalid-source and
  wrong-scope rejection. Cross-provider acceptance verification remains
  open.

  Commons now searches the approved query list with 20 results per query
  and an explicitly approved 40-result total cap, deduplicating source URLs
  and normalized file titles across queries. In the rebuilt Mac app, two
  local fixture queries produced five unique licensed results with both
  query origins displayed; download approval remained pending and no image
  contents were fetched. All 118 Python tests and Flutter analysis passed,
  including cross-query deduplication, early cap stopping and total-limit
  consent. Cross-provider acceptance verification remains open.
  The rebuilt Mac app retained three approved Wikipedia search results
  and omitted the fixture excerpt that fell below the minimum after Unicode
  normalization.
  The rebuilt Mac app exposed each Commons checkbox with its title,
  license, and download URL. Toggling a fixture checkbox excluded the image.
  In the rebuilt Mac app, Wikipedia selection controls exposed the
  article title when available and the source URL. Deselecting Astronomía
  reduced the fixture approval count from three to two.
  The rebuilt Mac app showed six licensed Commons fixture candidates
  and excluded the seventh because its license label exceeded 120 characters.
  An approved Commons fixture search in the rebuilt Mac app showed
  six file candidates and excluded a category result with image metadata.
  After Commons fixture search approval, the rebuilt Mac app showed six
  candidates and excluded the result whose download URL had no file path.
  An approved Commons fixture search in the rebuilt Mac app showed six
  candidates and excluded an image with a directional override in its license.
  After approved Commons fixture search, the rebuilt Mac app displayed
  the provider-supplied license terms URL before image download approval.
  After approving six local Commons fixture downloads, the rebuilt Mac
  app displayed the license terms URL beside the license in dataset preview.
  After approved Commons fixture search, the rebuilt Mac app displayed
  provider-supplied creator attribution as plain text beside the license.
  The rebuilt Mac app approved six Commons fixture downloads and showed
  the creator attribution alongside the license in dataset preview.
  The rebuilt Mac app displayed the Commons fixture credit in source
  review and retained it in dataset preview after six approved downloads.
  The rebuilt Mac app showed Attribution required for Commons fixture
  results at source review and after six approved downloads in preview.
  In the rebuilt Mac app, Commons fixture results with required attribution
  and no creator or credit directed users to the file page before approval.
  After six approved Commons fixture downloads, the rebuilt Mac app
  directed users to the file page for missing attribution in dataset preview.
  The rebuilt Mac app showed Commons fixture reuse restrictions during
  review and carried them into preview after six approved downloads.
  In the rebuilt Mac app, an approved Commons fixture search showed six
  candidates with readable restrictions and excluded a seventh whose
  restriction exceeded the metadata length limit.
  The rebuilt Mac app showed six Commons fixture candidates after approval
  and excluded the result with an array in place of restriction text.
  Approving a saved Commons fixture with an unreadable restriction in the
  rebuilt Mac app returned to search approval and started no downloads.
  The rebuilt Mac app sent the approved provider with the queries.
  Both approved fixture searches reached source review with explicit
  provider approval required. A regression test verified that omitting the
  provider leaves search awaiting approval and starts no worker.
  Local fixtures for Wikipedia and Commons both reached source review.
  In the Mac app, approving local Wikipedia and Commons fixture searches
  reached source review, and Activity history recorded each approved host.
  Additional provider integrations, project websites, and full-page
  collection remain open.
  A local fixture in the Mac app returned a malformed Unicode excerpt and
  a usable excerpt with a malformed title. After query and excerpt approval,
  the dataset preview showed three usable examples, retained the source with
  the malformed title without its title, and displayed the valid Astronomía title.
  In the rebuilt Mac app, deselecting one of three fixture sources
  changed the approval count to two. Approving produced a dataset preview
  containing exactly the two selected sources.
  After approving fixture queries in the Mac app, source review showed all
  three valid articles and omitted the result with a dot-segment page key.
  A second Mac fixture search included an invalid Unicode page key.
  Source review still showed all three valid articles for approval.

- [x] Provide web discovery and collection without a search API key. Show a
  built-in list of public data providers and let users add websites to a
  project. Discover candidate pages from the enabled providers without
  requiring page URLs from the user. Require approval before discovery
  contacts those providers, and show discovered URLs for approval before
  fetching pages for the dataset.
  Start with these providers. Use their public discovery endpoints without
  credentials and review reuse rights for each result before adding its
  content to a training dataset.

  | Workflow | Starter provider | Discover |
  | --- | --- | --- |
  | General knowledge and topic classification | English Wikipedia | [MediaWiki page search](https://www.mediawiki.org/wiki/API:REST_API/Reference/en#Search_pages) |
  | Images and captions | Wikimedia Commons | [MediaWiki search](https://commons.wikimedia.org/w/rest.php/v1/search/page?q=landscape) and file license metadata |
  | History, documents, and public collections | Library of Congress | [Catalog search](https://www.loc.gov/apis/json-and-yaml/requests/parameters/) |
  | Research literature | Europe PMC | [Publication search](https://europepmc.org/RestfulWebService) and available open-access records |
  | Entity tagging and knowledge graphs | Wikidata | [Public APIs and dumps](https://www.wikidata.org/wiki/Wikidata:Data_access) |
  | Economics and development indicators | World Bank Open Data | [Key-free Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392) |
  | Public notices and regulatory text | Federal Register | [Document search API](https://www.federalregister.gov/developers/documentation/api/v1) |
  | Company filings and financial text | SEC EDGAR | [Published indexes and data endpoints](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data); use a declared user agent and follow fair-access limits |
  | Bibliographic metadata | Crossref | [Public REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/); prefer identified requests and check reuse rights for abstracts |

  Use each provider's documented API, feed, or dump where available.
  For added websites, check the site's access rules and robots.txt before
  crawling. Treat automated access and permission to reuse content as
  separate checks.

  Match providers to the workflow and show the selected destinations before
  running discovery. Projects can add a public website as a source when
  the starter providers do not cover the topic.

  Acceptance verified locally on 2026-11-18. The provider-specific Mac app
  checks recorded above cover discovery previews, URL approval and reuse
  review for Wikipedia, Commons, Library of Congress, Europe PMC, Wikidata,
  World Bank, Federal Register and Crossref, plus SEC company lookup,
  submissions and filing previews. Provider selections persist per project,
  match the text/image workflows and block disabled-provider requests.
  The final rebuilt Mac app completed the website workflow from adding a
  source in project settings through robots/access review, approved link
  discovery, separate page requests and separate reuse decisions to a
  two-example dataset with both kinds of permission evidence. Fixture logs
  showed only the approved robots, starting-page and individual-page
  requests. No external collection, linked-resource fetching or training
  was performed. All 120 Python tests and Flutter analysis passed. New
  acceptance tests exercise every provider's missing-consent, valid-consent
  and disabled-provider dispatch boundary without API credentials.

- [x] Store collected page text and its source URL in a local index owned by
  the project. Search saved pages in later runs and preserve the index when
  updating the app. Include the index and provider settings in project
  export and restore so a fresh installation can reuse them without
  crawling again. Keep project data separate from the app release bundle.

  Partial delivery: successful approved web dataset preparation now stores
  source URLs, collected text, scope and permission evidence in a project-
  owned SQLite index alongside existing project data. The rebuilt Mac app
  began with an empty index, collected three local fixture pages, found
  only the astronomy page for a local text search, and reopened all three
  saved sources from a fresh training view after app relaunch. Search made
  no website requests. All 121 Python tests and Flutter analysis passed,
  including project isolation, repeated-source updates and persistence.
  Reuse in later datasets, project export/restore with provider settings,
  and installation-update storage verification remain open.

  Saved sources can now be selected for a later classifier dataset with
  explicit confirmation that their recorded content permission still
  applies. Revision checks reject changed text/evidence and sources from
  other projects. In the rebuilt Mac app, selecting two of three saved
  fixture sources produced exactly two locally labeled examples, retaining
  source URLs and reuse bases and identifying the local index as the origin.
  Logs showed no website requests. The final build exposed descriptive
  accessible source labels. All 122 Python tests and Flutter analysis
  passed. Export/restore with provider settings and installation-update
  storage verification remain open.

  Project settings now exports a versioned JSON snapshot of saved provider
  selections, website, instructions, reference files and the complete local
  page index with permission evidence. In the rebuilt Mac app, Export
  project data opened the native save dialog and saved a local fixture
  export, then reported three indexed sources. Reading that saved file
  verified all three full texts and URLs, both permission records, the two
  selected providers and the saved reference/settings. No website requests
  occurred. All 123 Python tests and Flutter analysis passed. Restore and
  installation-update storage verification remain open.

  The dashboard now restores a selected version-1 export as a separate
  project after confirmation, validating settings, references and pages
  before one atomic database write. The final rebuilt Mac app restored
  the native export, reported three indexed sources, reopened all three
  saved pages and returned only the astronomy page for a local search.
  Restored snapshots matched the exported settings, provider selections,
  references, texts, URLs and permission evidence exactly; the existing
  project was preserved. Logs showed no website requests. All 125 Python
  tests and Flutter analysis passed, including round-trip reuse and invalid
  restore rollback. Fresh-installation and app-update storage verification
  remain open.

  Project databases now default to a stable per-user data directory outside
  the release folder (Application Support/ALMG on macOS). First use copies
  a legacy database with SQLite backup and atomic publication, leaving the
  original intact and never replacing an existing stable database. Explicit
  database/data-directory overrides remain supported. The rebuilt Mac app
  reopened three migrated fixture sources, then reopened and searched them
  after switching to a second backend release folder with no project data.
  Both releases used the same isolated stable database; the legacy database
  remained byte-for-byte unchanged. All 127 Python tests passed with
  warnings treated as errors, and Flutter analysis passed. Fresh-install
  restore/reuse verification remains open.

  Final acceptance: a separate release folder and empty isolated user-data
  directory showed No projects yet in the rebuilt Mac app. Native-file
  restore imported the previously exported project and all three sources.
  The new Open Model Training action opened that restored project directly.
  Selecting two saved sources and confirming their recorded permission
  produced exactly two locally labeled examples, with both source URLs,
  content/access evidence and project-index origin preserved. Provider
  settings and references were restored with the project; no websites were
  contacted. Together with the verified release-folder replacement above,
  this completes the index, later-run search/reuse, export/restore and
  separate-storage acceptance criteria. All 128 Python tests passed with
  warnings treated as errors, and Flutter analysis passed.


- [x] Support importing labeled datasets and previewing examples and class balance. Flag missing labels, ambiguous examples, duplicates, and near duplicates. Keep related examples together when splitting data.
  One-word differences in phrases of 8–80 words now form review groups,
  including across explicit source groups, and stay together in evaluation
  splits. Similarity alone does not exclude examples or assert a label
  conflict. In the rebuilt Mac app, importing a three-row local CSV through
  the native Open panel showed one group, marked both Monday/Tuesday invoice
  variants for label review, left the unrelated telescope row unmarked and
  retained all three usable examples while training awaited approval.
  All 130 Python tests and Flutter analysis passed; regression checks cover
  split grouping, source-group connections, exact matches, short phrases,
  two-word differences and unchanged exclusions. Broader semantic ambiguity
  and near-duplicate detection beyond this bounded rule remain open.
  The same bounded phrase review now includes a single inserted or omitted
  word, regardless of input order, and keeps those rows in the same split.
  In the rebuilt Mac app, a native CSV import of an invoice sentence and
  its added “only” variant showed one group and marked both rows for label
  review. The unrelated telescope row remained unmarked, all three examples
  stayed usable and training still required approval. All 132 Python tests
  and Flutter analysis passed, including insertion/deletion grouping and
  phrase-length boundaries. Broader semantic ambiguity and similarity
  detection remain open.
  Similar-text groups with differing labels now receive a separate potential
  label-ambiguity warning and are prioritized in the five-row preview.
  These review candidates remain usable; exact/normalized conflicts keep
  their existing exclusions. The rebuilt Mac app imported a local CSV,
  displayed one potential-ambiguity group and marked both invoice variants,
  left the unrelated telescope example unmarked, and retained one fruit and
  two astronomy usable examples with training approval pending. All 133
  Python tests and Flutter analysis passed, including late-row prioritization
  and same-label negative cases. Broader semantic ambiguity remains open.
  An explicit local-model review now checks every classifier example in
  batches of four, validates indexed suggestions, stores short review
  reasons and prioritizes flagged rows. Labels and usable counts stay
  unchanged, with training approval still required. The rebuilt Mac app
  imported three unrelated fixture rows, ran Review label ambiguity locally,
  reported all three reviewed and one flagged, and displayed the mixed-topic
  example's reason while preserving class balance. This used deterministic
  local-model responses and no external requests. All 136 Python tests and
  Flutter analysis passed, including malformed later-batch preservation and
  interrupted-review recovery. Real-model semantic review quality remains
  unverified, so this requirement remains open.
  Final acceptance: the rebuilt Mac app ran label review with the existing
  verified mlx-community/Qwen3.8-27B-4bit checkpoint, with model loading
  offline and external collection blocked. For three imported local examples,
  Qwen flagged the mixed orchard-fruit/star-chart sentence and left both
  clear fruit and astronomy examples unflagged. All labels, class balance
  and usable counts remained unchanged, with training approval pending.
  Review results now save and display the model identifier; a regression
  assertion covers that provenance. Existing weights remained verified.
  All 136 Python tests and Flutter analysis passed. Combined with the
  recorded import validation, duplicate/near-duplicate warnings, ambiguous
  example review and source/variant split verification, the stated acceptance
  criteria are complete. Model suggestions remain advisory and can be wrong;
  this three-example check is not a general accuracy benchmark.
  The isolated Mac app showed one billing example and zero shipping examples
  in the class balance preview. The rebuilt app warned about the missing
  shipping class and left training approval pending. The backend also
  rejected a direct start request. The rebuilt Mac app imported a labeled CSV
  through the file picker and showed both class counts and example texts,
  including a quoted comma, while training approval remained pending.
  The rebuilt app flagged two duplicate rows and one text with conflicting
  labels in a local fixture. The isolated Mac app showed one near-duplicate
  group for two invoice examples differing only in punctuation. An offline
  fixture verified that punctuation variants and related source rows share
  a split group. The isolated Mac app trained a 48-row fixture with 24 such
  groups and reached inference preview with held-out macro F1 of 1.000.
  A regression test checks the recorded train, validation, and test assignments
  for each pair. Ambiguity beyond conflicting labels and near duplicates
  beyond normalized text variants remain open. A six-row fixture prepared
  by the backend and reopened in the rebuilt Mac app surfaced the final
  symbol-only row at line 7 with a label review warning. Training approval
  remained pending. A second fixture reopened in the rebuilt Mac app
  counted all six symbol-only rows in a seven-example dataset even though
  the preview shows at most five rows. The isolated Mac app counted one
  standalone accent with punctuation and displayed two distinct Devanagari
  words without the warning. Training still required approval.
  A regression test covers both standalone and attached combining marks.
  Starting training on a three-row fixture in the isolated Mac app showed
  the minimum of eight usable examples per label and named both shortfalls
  with their counts, billing with one and shipping with two.
  A 16-row fixture run in the isolated Mac app reported that its examples
  formed two independent groups against the five-group evaluation minimum.
  With the updated backend, approving that local fixture in the Mac app
  showed the two-group shortfall immediately and left approval available.
  A regression test confirms no training worker is queued.
  A second local Mac fixture passed the overall group minimum but had
  only two billing groups. Approval named billing and its count, explained
  the three-way split requirement, and left approval available.
  The rebuilt Mac app reopened a four-row fixture and showed one usable
  example per label after excluding a conflicting pair. Both shortfalls
  appeared before training approval.
  A six-row CSV imported in the isolated Mac app showed one usable example
  per label after excluding both copies of a duplicate and both rows of a
  conflicting pair. Preview and training now share the exclusion rules.
  The rebuilt Mac app reopened that dataset, reported one repeated row,
  and explained that training and evaluation skip every copy. Training
  still required approval.
  The rebuilt Mac app replaced that four-example dataset with a two-example
  CSV through the Open panel in the same training conversation. The preview
  showed the new examples and training still required approval.
  Replacing that dataset with a CSV missing a label showed the line 2
  error and preserved both examples. An offline regression test verifies
  that validation rejects the replacement before starting a worker.
  Approving the two-example fixture in the isolated Mac app reported one
  usable example for each label against the minimum of eight. The backend
  kept the dataset ready and the Mac app still offered CSV replacement.
  An offline regression test confirms that rejecting the approval leaves
  the dataset ready and starts no training worker.
  Approving a saved dataset without usable counts in the isolated Mac app
  also reported one usable example per label and kept CSV replacement
  available.
  In the rebuilt isolated app,
  importing a three-row CSV with ASCII and full-width invoice text showed
  one near-duplicate group and left training awaiting approval. The preview
  now labels the count as Unicode and punctuation variants, verified after
  rebuilding and reopening the saved dataset. A local fixture also verified
  that the Unicode variants share a split group and an unrelated row stays separate.
  In the isolated Mac app, importing the variants with different labels
  showed one conflicting-label group and left training awaiting approval.
  A four-row CSV submitted to the isolated backend combined exact repeats
  and punctuation variants with conflicting labels. The running Mac app
  showed two duplicate rows and one conflicting group, with training still
  awaiting approval.
  Reopening this fixture in the rebuilt Mac app showed the instruction to
  review conflicting labels before approving training. A fresh import in the
  rebuilt Mac app marked both conflicting preview rows and left the unrelated
  example unmarked, with training approval still pending. A seven-row CSV
  imported through the isolated Mac app showed its last two rows first in
  the five-row preview because their labels conflicted. A second seven-row
  fixture showed its two same-label Unicode variants first and reported one
  near-duplicate group while training approval remained pending. A separate
  Mac import grouped “Pay invoice” and “Pay invoice!” together and kept
  training approval pending. The isolated Mac app also flagged “Invoice” and
  “Ｉｎｖｏｉｃｅ!” as one group. Single tokens shorter than five characters
  still use exact matching. In the rebuilt
  Mac app, a quoted multiline CSV record showed its ending line as 3 and the
  following record showed line 4 while training awaited approval. The isolated
  Mac app also imported the same fixture with carriage-return line endings
  and showed both records at the same line numbers. An unterminated quoted
  record ending on line 4 produced “Invalid CSV near line 4” in the Mac app
  and left dataset approval pending.
  Importing a CSV with a blank label showed the line number and missing-label
  error in the isolated Mac app and left dataset approval pending. After rebuilding,
  the same import displayed the validation message without the exception prefix.
  Importing an invalid CSV through the native Open panel in the isolated Mac
  app identified the unrecognized label 'biling' on line 2, left dataset
  approval pending, and showed zero examples.
  The rebuilt Mac app rejected a non-UTF-8 CSV selected in the native Open
  panel and asked the user to save it as UTF-8. Dataset approval stayed
  pending with zero examples.
  Two CSVs selected through the isolated Mac app reported missing text
  and text exceeding 3000 characters on line 2, respectively. Both left
  dataset approval pending with zero examples.
  Retrying through the native Open panel in the rebuilt Mac app showed the
  new missing-text error and hid the saved unrecognized-label error.
  The Mac app imported a CSV with an optional `group` column and showed all
  three examples awaiting training approval. A local split fixture verified
  that differently worded rows sharing a group stay together. The isolated
  Mac app trained a 32-row CSV with a duplicate shared by two source groups
  and reached inference preview with held-out macro F1 of 1.000. The saved
  split assigned both groups to the test set and excluded the duplicate.
  A Mac CSV import grouped a Devanagari punctuation variant while preserving
  a distinct vowel mark and showing no false label conflict.
  The isolated Mac preview showed one duplicate and one conflict for two
  Unicode encodings of café. The unaccented cafe row had neither warning.
  A local split check kept both accented encodings together.
  Training in the isolated Mac app reached inference preview with held-out
  macro F1 of 1.000. The saved training dataset contained all three splits
  and excluded both accented duplicates.
  A second run approved in the isolated Mac app also reached inference
  preview with held-out macro F1 of 1.000. All three saved splits excluded
  both punctuation variants flagged for conflicting labels.
  The rebuilt Mac app showed one conflicting group before approval and
  explained that training and evaluation skip those examples.
  The automated split test now checks that conflicting variants are
  excluded and all 48 same-label examples stay in their assigned splits.
  The isolated Mac app accepted spaces around the text, label, and group
  headers and previewed both rows while training awaited approval.
  A second Mac import read the columns in group, label, text order and
  showed one correctly labeled example per class before training approval.
  A local CSV fixture with whitespace-only and separator-only rows yielded
  two examples. The isolated Mac app displayed the original ending lines
  3 and 5, with training approval still pending.
  The isolated Mac app imported a CSV with two blank rows before its
  header and previewed both examples at their original lines, 4 and 5.
  Training approval remained pending.
  The rebuilt Mac app displayed source group A on both related CSV rows and
  group B on the unrelated row before training approval.
  In the rebuilt Mac app, both repeated rows showed Duplicate text and both
  punctuation variants showed Near-duplicate text. Training awaited approval.
  The isolated Mac app reopened a seven-row offline search fixture and
  showed the last two rows first because their labels conflicted. Training
  still awaited approval.
- [x] Persist jobs and progress across backend restarts. Show logs, metrics, and artifact locations. Add cancellation and resume where the training recipe can restore a checkpoint.
  After a backend restart, the isolated Mac app reopened a saved classifier
  candidate with its activity, held-out score, and folder containing the model
  and dataset. In the rebuilt Mac app, cancelling while waiting for idle
  time stopped a fixture before training. The cancelled state survived a
  backend restart. In the rebuilt Mac app, cancelling a running fixture
  stopped it at a progress boundary and produced no model candidate.
  The isolated Mac app also reopened an interrupted classifier fixture after
  a backend restart. Approving training again reused the saved dataset and
  reached inference preview. An offline regression test confirms recovery
  reloads the saved rows and waits for approval. Fitting restarts from the
  beginning. The rebuilt Mac app retained the saved idle preference and
  evaluated the recovered run against its original 0.92 target. Resuming from
  a training checkpoint remains open.
  Classifier training now atomically saves completed candidate fits and
  validation trials, bound to the dataset, labels, target, repair option and
  scikit-learn version. Matching state skips completed candidates after a
  backend restart; changed datasets restart candidate fitting. The rebuilt
  Mac app approved a 48-row fixture, saved candidate one, then recovered
  after the isolated backend was stopped before candidate two. Approval in
  the relaunched app logged reuse of one completed candidate, fitted the
  remaining three and reached inference preview with validation and held-out
  macro F1 of 1.000. Activity history displayed checkpoint locations. All
  138 Python tests and Flutter analysis passed; resumed metrics and split
  assignments match uninterrupted training. An unfinished individual fit
  still restarts, and a user action to resume a deliberately cancelled job
  remains open.
  Final acceptance: cancelled classifiers can reopen their validated saved
  dataset only after the previous worker stops, and training still requires
  fresh approval. In the rebuilt Mac app, a 48-row fixture was cancelled
  after candidate one was saved. Cancellation and the checkpoint survived
  backend restart, with no completed model created. Reopen cancelled training
  dataset restored class balance and approval controls; approval then reused
  candidate one and reached inference preview with validation and held-out
  macro F1 of 1.000. Activity history showed the reused checkpoint and saved
  artifact location. All 140 Python tests and Flutter analysis passed,
  including missing confirmation, active-worker rejection, invalid saved
  rows and worker cleanup. Checkpoint resume is supported between completed
  classifier candidates; an individual fit restarts. The stated persistence,
  progress/logs/metrics/artifacts, cancellation and supported-resume criteria
  are verified.
- [x] Keep validation separate from final testing. Use validation errors to guide a bounded retry, retain the best candidate, and report the final score on a held-out dataset. Test the full path from an approved dataset to a reloadable model and report.
  The rebuilt Mac app ran one opt-in retry from validation errors using a local
  Qwen fixture and reported a separate held-out score. The saved dataset
  included the novel retry example and rejected the punctuation variant. A
  second Mac run reached preview with held-out macro F1 of 0.245 and kept
  the novel example while rejecting a variant of a removed duplicate.
  After restarting the isolated backend, the Mac app ran the saved retry
  candidate on an unseen invoice prompt and predicted billing. Release stayed
  disabled because the candidate missed its evaluation target. With a passing
  local retry fixture, the Mac app approved training, reported validation
  macro F1 of 0.748 and held-out macro F1 of 0.667 against a target of 0.590,
  and released the model, dataset, and evaluation report after preview approval.
  Reloading the exported model reproduced the preview label “shipping” for
  “Silver ticket status,” and the report recorded the second training round.

## P2 · Improve chat and project work

- [x] Save unsent drafts across app restarts. Test that a backend outage preserves the draft and exposes any partial response without duplicating a saved turn.
  Chat now saves the pending payload and retry token before sending, retains
  interrupted text with the draft, and restores recovery state across app
  restarts. Offline recovery displays the saved draft and interrupted reply.
  The rebuilt isolated Mac app restored an unsent draft after restart, then
  survived a fixture connection loss after the backend committed the reply
  but before its completion event arrived. After stopping the backend and
  restarting the app again, both draft and partial reply were visible offline.
  Reconnection and retry reused the same saved token and recovered the full
  response. Logs and SQLite verified one generation, one chat and exactly
  one user/assistant pair. Existing preferences were preserved by using an
  isolated fixture state file. All 141 Python tests, 8 Flutter tests and
  Flutter analysis passed, including lost-acknowledgement idempotency.
- [x] Expand support for PDF and image attachments. Show which text or image content the model can use, and cite filenames and page numbers when available.
  Partial delivery: the composer now previews the exact bounded text made
  available to Qwen, including PDF page markers, with an explicit explanation
  that image visuals and PDF layout are not provided as context. UTF-8 text
  files also receive previews; binary content is rejected as text. The
  12,000-code-point bound matches the backend without splitting Unicode
  surrogate pairs. In the rebuilt Mac app, a two-page local PDF selected
  through the native Open panel showed both pages in the expandable preview.
  Actual local Qwen answered from page 2 and cited the filename and page;
  captured model context matched the displayed text and page markers. All
  141 Python tests, 10 Flutter tests and Flutter analysis passed. Image OCR
  and unreadable-attachment app verification remain open.
  Final acceptance: image previews now identify recognized OCR text and
  advise reviewing recognition errors; .tif and .heif aliases use the native
  image path. In the rebuilt Mac app, selecting a local .tif through the
  native Open panel produced the expected recognized text with its filename
  and OCR limitation note. Actual local Qwen answered from that text and
  cited the image filename; captured context matched the preview. A blank
  PNG displayed the no-readable-text message and explicitly said its visuals
  were unavailable, with a request to describe it. Combined with the verified
  PDF page preview and page citation, the stated attachment criteria are
  complete for the text/OCR context path. All 141 Python tests, 11 Flutter
  tests and Flutter analysis passed. Direct visual interpretation and PDF
  layout analysis are not provided by this path and are labeled accordingly.
- [x] Add full-text conversation search, Markdown export, and controls for whether the model can draw on other conversations.
  Partial delivery: conversation menus now save Markdown through the native
  file dialog as well as copying it. Both actions use a shared formatter
  that preserves message formatting, order, Unicode and attachment filenames
  while escaping title/filename metadata. In the rebuilt isolated Mac app,
  searching “violet lantern” returned Inventory question even though the
  phrase occurred only in its assistant reply, excluding the unrelated chat.
  Save as Markdown produced a local file containing only that conversation,
  with its title, user/assistant sections and attachment filename. All 141
  Python tests, 13 Flutter tests and Flutter analysis passed. App-level
  verification of cross-conversation recall controls remains open.
  Final acceptance: the conversation view now exposes Use other conversations
  before sending, sharing its persisted preference with Settings. In the
  rebuilt Mac app, enabled recall sent true and included a related message
  from the selected fixture project; disabled recall sent false and omitted
  that message while retaining current-thread history. Captured request and
  context fixtures verified that the other project's matching message was
  excluded in both cases. After app restart, the chat switch and Settings
  both remained off. All 142 Python tests, 13 Flutter tests and Flutter
  analysis passed. Together with the verified message-body search and native
  Markdown export above, all stated acceptance criteria are complete.
- [x] Test project instructions, reference files, and chat branches together. Verify that a branch preserves its source conversation and stays in the same project.
  Branch responses now identify their source and project, and the Mac app
  confirms both after creating a branch. An integrated local regression
  covers project instructions, reference snippets, inherited PDF page text,
  other-project exclusion and source preservation together. In the rebuilt
  isolated Mac app, project settings displayed the instruction and reference
  file; branching the saved answer confirmed Branch fixture project and its
  source conversation. A follow-up with recall disabled received the expected
  fixture response only after asserting all inherited context. Reopening the
  original showed its unchanged two messages; SQLite confirmed the branch
  remained in the same project with four messages. All 143 Python tests,
  13 Flutter tests and Flutter analysis passed. No external collection or
  model download was performed.

## P3 · Extend the dynamic workbench and platform support

- [x] Define a training recipe interface for dataset format, hardware needs, parameters, metrics, and export format. Validate a small LoRA run on Apple silicon before adding more recipes.
  Partial delivery: a versioned recipe-contract catalog now describes the
  two existing recipes' dataset formats, hardware, parameter types/defaults,
  metric keys, exported artifacts and resume limitations. Planning records
  an independent contract snapshot in each new job; the planner's supported
  IDs come from the catalog, and release packaging includes the module.
  In the rebuilt Mac app, Training recipe details displayed both classifier
  and experimental image contracts with all sections, while dataset approval
  remained pending. Saved fixture jobs retained version-1 snapshots. All
  148 Python tests, 13 Flutter tests and Flutter analysis passed, including
  API routes, snapshot independence, unknown-recipe rejection and unchanged
  restart of a legacy job without contract metadata. No recipes were added.
  LoRA validation and further execution-interface integration remain open.
  Training approval now validates recipe-specific parameter types, finite
  target bounds, supported settings and contract identity/version before
  queuing a worker. Contract defaults apply to omitted flags; legacy image
  requests with a false classifier-retry flag remain accepted, while the
  current image UI omits that unsupported option. In the rebuilt Mac app,
  both a 48-row classifier and the 45-example local shape recipe passed
  validated approval and reached inference preview with held-out scores of
  1.000. Saved jobs retained normalized settings and matching contract IDs.
  All 151 Python tests, 13 Flutter tests and Flutter analysis passed, including
  invalid-target/type/version rejection and no-worker failure behavior.
  LoRA validation and remaining execution-interface integration stay open;
  no recipe was added.
  Evaluation output now validates required metric keys, numeric finite score
  bounds, the approved target and below-target pass claims before a candidate
  is saved for preview. Invalid output fails the job without saving a preview
  candidate. All 153 Python tests passed, including invalid-output persistence
  protection and both local and Commons image metric variants. In the rebuilt
  Mac app, approval of fresh local fixtures trained a 48-row classifier and
  45-example shape model to inference preview, each showing a held-out score
  of 1.000 against the approved 0.800 target. No external collection occurred.
  LoRA validation and remaining interface integration are still open.
  Candidate persistence now checks the existing model export/runtime formats:
  a scikit-learn pipeline for classifiers, and the expected versioned image
  format with 48x48 size and finite JSON values. Unsupported models fail before
  any preview candidate is saved. All 155 Python tests passed, including both
  image variants, invalid formats/sizes/nonfinite values and failure without
  candidate persistence. In the rebuilt Mac app, fresh 48-row classifier and
  45-example shape fixtures both passed approval, training and the new format
  checks to reach inference preview with held-out scores of 1.000. No external
  collection or downloads occurred. LoRA validation and remaining interface
  integration stay open; no recipe was added.
  Image candidate validation now checks complete learned payload dimensions:
  all shape/position masks, bounded RGB colors and background, and caption
  vocabulary/coefficient compatibility. Missing, nonnumeric or incorrectly
  shaped payloads are rejected before preview persistence. All 156 Python
  tests passed, including malformed payload cases. In the rebuilt Mac app,
  the fresh 45-example shape fixture trained to held-out accuracy 1.000;
  submitting "a red circle and a blue square" rendered both requested shapes
  in the inference preview. No external collection or downloads occurred.
  LoRA validation and remaining recipe-interface integration stay open.
  Released bundles now include recipe-contract.json with the saved approval
  contract snapshot and actual recipe-specific execution settings. Legacy
  jobs use an explicitly labeled catalog fallback without rewriting the job.
  The catalog lists this sidecar. All 158 Python tests passed, covering both
  provenance paths, independent snapshots and release bundle contents. In the
  rebuilt Mac app, a fresh 45-example shape model trained to accuracy 1.000,
  rendered a red circle and blue square, and completed the explicit release
  action. Its four-file bundle contained model.json, dataset.jsonl, report.json
  and the new sidecar; the exported contract exactly matched the saved job,
  with target 0.800 and idle=false. No external collection occurred. LoRA
  validation and remaining interface integration stay open.
  Training now checks recipe dataset row structure before invoking a trainer:
  nonempty text, approved classifier labels and groups, or image split and
  required shape/caption fields. Image datasets require both train and test
  rows. Invalid datasets fail with an example-specific error without calling
  the trainer or consuming the prepared rows. All 160 Python tests passed.
  In the rebuilt Mac app, fresh 48-row classifier and 45-example shape fixtures
  passed approval and the structural checks, then reached inference preview
  with held-out scores of 1.000. No external collection or downloads occurred.
  LoRA validation and remaining recipe-interface integration are still open.
  A shared execution-variant resolver now binds dataset modes to recipe IDs
  for approval, trainer selection and dataset/model/metric validation. A
  classifier can no longer select the image trainer through web_images mode;
  unsupported image/text source combinations are rejected before queuing.
  Legacy missing-mode jobs retain local behavior. All 162 Python tests passed,
  including supported legacy/source combinations and no-worker rejection.
  In the rebuilt Mac app, fresh 48-row classifier and 45-example shape fixtures
  followed their intended trainers and reached preview with held-out scores
  of 1.000. No external collection occurred. LoRA validation and remaining
  recipe-interface integration stay open; no recipe was added.
  Supported dataset modes and their execution variants now come from the
  versioned recipe catalog rather than a second hardcoded routing table.
  Recipe details displays deduplicated source labels; older saved snapshots
  without mode metadata still open. All 163 Python tests, 13 Flutter tests
  and Flutter analysis passed. In the rebuilt Mac app, both recipe dialogs
  displayed their supported sources, and the fresh 45-example shape fixture
  trained through its catalog-defined mode to preview with accuracy 1.000.
  The installed environment has MLX inference but no mlx_lm package or ALMG
  LoRA workflow; small LoRA validation remains unverified. No recipe, external
  collection or downloads were added. Remaining recipe integration stays open.
  Image dataset validation now checks numeric mask/RGB bounds, complete
  shape/color training coverage, and bounded, readable 48x48 RGB PNG inputs
  for the Commons recipe. All 165 Python tests passed using local numeric and
  encoded-image fixtures. In the rebuilt Mac app, approving an image dataset
  with RGB=256 failed with the displayed example-1 bounds error and saved no
  preview candidate. A separate valid 45-example fixture passed the same gate
  and trained to inference preview with held-out accuracy 1.000. No external
  collection occurred. LoRA validation and remaining integration stay open.
  Existing trainers now run through one recipe execution interface that
  resolves the catalog variant, validates settings and input/output datasets,
  invokes the registered local trainer, and validates metrics and model before
  returning a preview candidate. Orchestration retains scheduling, cancellation,
  repair callbacks, checkpoint paths and persistence. Prepared rows are consumed
  only after successful execution. All 167 Python tests passed, including
  callback/checkpoint forwarding, malformed returns and real shape execution.
  In the rebuilt Mac app, fresh 48-row classifier and 45-example shape fixtures
  both trained through this interface to preview with held-out scores of 1.000.
  Existing-recipe execution integration is delivered; the required small LoRA
  run on Apple silicon remains unverified, so this item stays open. No external
  collection, downloads or new recipes were added.
  Added an opt-in local LoRA runtime smoke test in Recipe details. It uses
  generated tensors, a frozen tiny projection and rank-2 adapters on Metal;
  verifies loss improvement and frozen base weights; then saves/reloads the
  adapter in a temporary directory and checks matching outputs. It shares the
  dedicated inference worker and downloads or modifies no existing weights.
  The API requires explicit fixture confirmation and release packaging includes
  the lazy-loaded module. All 169 Python tests, 13 Flutter tests and Flutter
  analysis passed. In the rebuilt Mac app, Run local LoRA fixture displayed:
  Metal GPU, rank 2, 100 steps, loss 0.341811 to 0.000198, unchanged base weights
  and adapter reload error 0.0. This verifies the tiny projection runtime only;
  a representative language-model LoRA run remains unverified, so the item
  stays open and no additional recipe is enabled.
  Completed the small Apple-silicon LoRA validation with a tiny causal
  self-attention language model, replacing the projection-only smoke test.
  Generated four-token cycles use length-8 training and distinct length-12
  held-out contexts. Only the rank-2 output adapters train (24 parameters);
  all 256 initialized base parameters remain frozen. In the rebuilt Mac app,
  Run local LoRA fixture completed 100 Metal GPU steps: next-token loss fell
  from 1.532488 to 0.007317, held-out accuracy was 100%, and autoregressive
  generation produced 0 1 2 3 0 1 2 3 0 1 2 3. Changing a future token left
  earlier logits unchanged; causal-prefix and saved-adapter reload errors were
  both 0.0. All 171 Python tests passed with ALMG_METAL_TESTS=1 (including the
  real GPU run), plus 13 Flutter tests and clean Flutter analysis. Together
  with the verified existing-recipe contract/execution/export integration
  above, this satisfies this item's interface and small-run criteria. This is
  a deliberately tiny offline validation fixture, not a production fine-tuning
  recipe; no additional recipe, downloads or external collection were enabled.
- [ ] Check available memory and disk before training. Verify idle detection, power checks, sleep and wake recovery, and safe resume after the machine becomes busy.
  Partial delivery: training approval checks available memory and free disk
  against a minimum reserve scaled by prepared dataset size; a second check
  runs immediately before training after idle waiting. Successful measurements
  are saved with the job. Low resources leave/return the prepared dataset to
  fresh approval, with an actionable message and no trainer invocation.
  macOS memory uses vm_stat page size plus free/inactive/speculative pages;
  disk is checked on the existing ancestor of the training storage directory.
  The 175-test Python suite passed with the unrelated opt-in Metal test skipped
  (174 executed). Tests cover memory parsing, dataset-scaled estimates, low
  memory/disk, no queued worker, and resource loss after queuing. In the rebuilt
  Mac app, a local low-memory fixture displayed 0 MiB available versus a
  258 MiB reserve and retained training approval. Retrying with real system
  resources trained the same 45-example dataset to preview at accuracy 1.000;
  saved resource measurements exceeded both estimates. No external collection
  occurred. Idle/power, sleep/wake and busy-machine resume verification remain
  open; estimates are admission checks rather than memory-usage guarantees.
  Idle-gated training now rechecks idle/AC eligibility at reported training
  boundaries. If the device becomes busy or loses AC, it pauses between steps,
  retains the worker/dataset and cancellation controls, then rechecks resources
  before resuming. Individual fits are not interrupted. The 179-test Python
  suite passed (178 executed; unrelated opt-in Metal test skipped), covering
  pause/resume, cancellation, immediate-training bypass, macOS 600-second idle
  threshold, AC/battery distinction and probe timeout failure. In the rebuilt
  Mac app, a local fixture became busy after initial admission: the UI showed
  Training paused between steps, then automatically resumed after the fixture's
  20-second busy period and reached preview at accuracy 1.000. The saved job
  retained idle=true and both pause/resume activity entries. No external
  collection occurred. Physical sleep/wake recovery and real-device busy/power
  transition verification remain open; the native transition used local fixtures.
  Training now checks wall versus monotonic elapsed time at progress
  boundaries, including after an idle wait. A gap over five seconds (suspended
  uptime or a forward clock adjustment) conservatively returns the retained
  dataset to fresh approval instead of proceeding automatically. Existing
  checkpoints are retained and individual fits are not interrupted. The
  181-test Python suite passed (180 executed; opt-in Metal test skipped),
  including ordinary elapsed work and discontinuity recovery. In the rebuilt
  Mac app, an injected 60-second wall/one-second uptime transition displayed
  the sleep-or-clock-change recovery message and preserved all 45 examples.
  Explicit reapproval trained the retained dataset to preview at accuracy
  1.000. No external collection occurred. Actual physical sleep/wake and real
  busy/power transitions remain unverified; this is a conservative clock guard,
  not a platform sleep notification implementation.
  Idle/power probing now exposes live readiness details used by both the
  scheduler and a read-only Recipe details action. Waiting jobs display AC
  confirmation and progress toward the 600-second idle threshold; probe errors
  remain ineligible. Readiness is response metadata, not saved approval state.
  The 184-test Python suite passed (183 executed; opt-in Metal test skipped),
  plus 13 Flutter tests and clean analysis. In the rebuilt Mac app, the real
  host probe showed Device ready for idle-gated training, AC connected and
  600/600 seconds; a preceding real-probe admission also trained the local
  shape fixture to preview at accuracy 1.000. A controlled busy fixture then
  showed 42/600 seconds in the waiting UI, and Cancel queued training stopped
  it. No external collection occurred. Physical sleep/wake and actual
  busy/power transitions remain open; the busy state was a local fixture.
  Backend restart recovery now reopens valid prepared datasets for interrupted
  image training as well as classifier training. Waiting image jobs explain
  that fitting restarts without a partial-fit checkpoint; classifier waits
  retain the matching-checkpoint explanation. Fresh approval is required and
  no worker starts during restore. Invalid saved image rows are rejected.
  The 186-test Python suite passed (185 executed; opt-in Metal test skipped),
  covering in-training and waiting recovery and malformed rows. In the rebuilt
  Mac app, a saved in-training image fixture reopened with its recovery message
  and all 45 examples at approval; explicit reapproval reached preview at
  accuracy 1.000. The prepared dataset's SHA-256 was unchanged. No external
  collection occurred. Physical sleep/wake and actual busy/power transitions
  remain unverified, so this scheduler requirement stays open.
  Cancelled image jobs now support the same explicit saved-dataset reopen
  action as classifiers. Reopening requires confirmation, waits for the old
  training worker to stop, validates saved rows against the recipe, and returns
  to fresh training approval. The image UI explicitly says fitting restarts
  without a partial-fit checkpoint. The 188-test Python suite passed (187
  executed; opt-in Metal test skipped), plus 13 Flutter tests and clean analysis.
  In the rebuilt Mac app, a saved cancelled image job showed the new action;
  reopening restored 45 examples at approval, and explicit approval trained to
  preview with accuracy 1.000. The dataset SHA-256 stayed unchanged. No external
  collection occurred. Physical sleep/wake and real busy/power transitions
  remain open.
  macOS now observes NSWorkspace sleep/wake notifications and forwards them
  through a process-wide Flutter channel to the local backend. Active queued,
  waiting or training jobs require fresh approval at the next safe boundary;
  prepared data and existing checkpoints remain retained. New approval clears
  the event guard. A clearly labeled local notification fixture exercises the
  actual native observer/channel/HTTP path without suspending the Mac. The
  190-test Python suite passed (189 executed; opt-in Metal test skipped), plus
  14 Flutter tests and clean analysis. The loopback test verifies desktop
  authorization and exact Content-Length framing. In the rebuilt Mac app, the
  native fixture delivered both sleep and wake events, returned a waiting
  45-example image job to approval with the recovery message, and explicit
  reapproval reached preview at accuracy 1.000. Saved activity confirms both
  events. No external collection or power-setting changes occurred. Actual
  physical suspend/resume and real busy/power transitions remain unverified.
  The final transition into preview now rechecks native power-event and
  clock-discontinuity guards inside the candidate persistence lock. Events
  arriving during the final evaluation, after its last progress callback,
  cannot bypass renewed approval or consume the retained dataset. The 192-test
  Python suite passed (191 executed; opt-in Metal test skipped), including
  final-evaluation power and clock gaps with no candidate persistence. In the
  rebuilt Mac app, a local fixture injected wake after real image evaluation:
  the job returned to approval and candidate.json did not exist. Explicit
  reapproval then reached preview at accuracy 1.000. No external collection
  occurred. Physical suspend/resume and actual busy/power transitions remain
  unverified, so this requirement stays open.
  Native power-event delivery now retries transient socket/timeout/server
  failures up to three times with a stable event ID; permanent HTTP rejections
  are not retried. The backend deduplicates its most recent 256 event receipts
  in memory, preventing an acknowledged retry from invalidating fresh approval
  twice within the same backend lifetime. The 193-test Python suite passed
  (192 executed; opt-in Metal test skipped), plus 16 Flutter tests and clean
  analysis. In the rebuilt Mac app, a local server returned 503 on the first
  sleep and wake deliveries. Each retried with its original ID and received
  200; saved activity contained exactly one entry per event. The waiting job
  returned to approval and explicit reapproval reached preview at accuracy
  1.000. No external collection occurred. Physical suspend/resume and real
  busy/power transitions remain unverified; this requirement stays open.
  Power-event receipts now survive backend restart in an atomically replaced,
  version-1 cache bounded to 256 entries. Receipts are saved before delivery is
  acknowledged and restored with jobs. Legacy absence is accepted; malformed
  cache input is ignored without rewriting it on load. The 195-test Python
  suite passed (194 executed; opt-in Metal test skipped), covering receipt
  round-trip, atomic replacement, legacy absence and malformed input. In the
  rebuilt Mac app, a fresh backend restored a saved queued job and an event
  receipt produced by a separate fixture process. After native reapproval,
  replaying the acknowledged wake ID returned 200 without changing waiting
  state or adding another wake activity. Cancel/reopen and immediate approval
  then trained the same 45-example dataset to preview at accuracy 1.000. No
  external collection occurred. Physical suspend/resume and real busy/power
  transitions remain unverified; this requirement stays open.
- [ ] Validate the Windows build and a CPU training run on Windows. Evaluate GPU support and decide whether planning runs locally on Windows or uses a paired Mac.

P3-LMF-01 partial progress · 2026-11-19 (requirement remains open):
- Added trusted local recipe registration with version/schema validation,
  dependency checks, duplicate rejection and independent snapshots. Planner
  discovery reads the registry per request. Existing classifier and image
  recipes register through this boundary; no new student recipe is enabled.
- Rebuilt and launched the macOS app against isolated local fixtures. Through
  the desktop UI, opened both version-1 recipe details and verified supported
  sources, parameters, metrics and exports. Approved classifier training on 48
  examples: validation and held-out macro F1 1.000, ready for inference preview.
  Approved image training on 45 examples: held-out pixel accuracy 1.000, ready
  for inference preview. Also exercised cancel/reopen and renewed image approval.
  Local API preview previously returned fruit and a generated PNG respectively.
  No external collection occurred. Accessibility permission restored desktop
  verification; the earlier UI-access blocker is resolved.
- Verification: 197 Python tests (196 passed, one opt-in Metal test skipped),
  16 Flutter tests passed, Flutter analysis clean. Existing stored recipe
  contracts retain their schema and contents; generated artifacts stay outside Git.
- Remaining: registered from-scratch decoder construction, confirmed approach
  selection, versioned pipeline stages, reproducibility manifest and complete
  acceptance verification. Physical power checks and Windows validation remain
  open independently and do not block this roadmap.

P3-LMF-01 partial progress · run reproducibility records · 2026-11-19:
- Completed classifier/image candidates now capture a version-1 run-manifest.json
  alongside their model: evaluated dataset and partition hashes, recipe/settings
  snapshot and hash, evaluation/hash, actual classifier split seed, CPU/runtime
  dependency versions, component source hashes and candidate model hash. The
  existing classifier estimators retain default random_state; the record explicitly
  avoids promising bitwise reproduction. This is not the full future LM manifest.
- Recipe details opens an integrity-checked, selectable run record in ALMG.
  Reading checks model/dataset contents and settings/evaluation hashes. Releases
  retain the captured training environment and bind the exported model file.
  Older candidates without a record return an actionable message; no migration or
  retroactive training metadata is written to existing jobs. The release package
  includes the new backend module.
- Local app verification: rebuilt/launched macOS ALMG with isolated generated
  fixtures. Approved classifier training through the desktop UI (48 rows, held-out
  macro F1 1.000), opened its run record and observed train/validation/test counts
  29/9/10, split seed 0, dependency versions and hashes. Restarted the fixture
  backend from persisted jobs, ran native model preview, approved release in ALMG,
  and reopened the exported model.joblib record in the desktop dialog. Training
  runtime, component hashes, dataset and partition hashes matched the candidate.
  The live image workflow also produced a verified record for 45 rows split 36/9,
  with held-out pixel accuracy 1.000. No external collection occurred.
- Verification: 201 Python tests (200 passed, one opt-in Metal test skipped), all
  16 Flutter tests passed, Flutter analysis clean. Added integrity/tampering,
  restart/legacy read compatibility and release-runtime preservation coverage.
- Remaining: from-scratch decoder registration/construction, explicit approach
  selection, full versioned pipeline-stage interfaces, approval revision and
  checkpoint lineage for future LM execution, and complete acceptance verification.
  P3-LMF-01 remains open; physical power/Windows blockers remain independent.

P3-LMF-01 partial progress · training approval revisions · 2026-11-19:
- Each explicit training approval now captures a unique receipt ID, UTC time
  and content revision binding the goal, mode, labels, recipe/settings snapshot,
  prepared row count and prepared-dataset hash. Queued execution validates this
  binding before invoking a trainer. Changed inputs retain the dataset and return
  to fresh approval. A renewed approval has a new receipt ID even when its content
  revision is unchanged. Run records preserve the receipt and its integrity hash.
- Legacy jobs without a receipt remain readable and do not receive fabricated
  approval history. New approval through the existing route captures the receipt;
  no API parameter or historical schema rewrite is required.
- Local verification: rebuilt/launched ALMG with a fresh isolated image fixture,
  selected immediate execution and explicitly approved training in the desktop UI.
  The 45-row run reached preview at pixel accuracy 1.000. Opened the native run
  record and verified the receipt, revision, prepared-dataset/settings binding and
  hash; restarted the backend from persisted jobs and reopened the record in ALMG.
  Receipt and integrity hash matched exactly after restart. No external collection.
- Verification: 203 Python tests (202 passed, one opt-in Metal test skipped), all
  16 Flutter tests passed, Flutter analysis clean. Tests cover changed dataset,
  settings, goal and receipt rejection; renewed approval identity; legacy JSON
  compatibility; and queued recovery without trainer execution or dataset loss.
- Remaining: from-scratch decoder registration/construction, explicit choice of
  approach, full versioned stage interfaces, checkpoint lineage and complete
  acceptance verification. P3-LMF-01 remains open; hardware blockers stay separate.

P3-LMF-01 partial progress · classifier checkpoint lineage · 2026-11-19:
- Completed classifier evaluations and their run records now include a versioned
  checkpoint lineage entry: compatibility key, fresh/resumed/rejected state,
  number of restored candidates, source checkpoint hash and final checkpoint hash.
  Mismatched or unreadable checkpoints are identified separately and retain the
  existing safe fresh-fit behavior. Image recipes still restart fitting and do not
  claim checkpoint support. Existing stored jobs and checkpoints need no rewrite.
- Local app verification: rebuilt/launched macOS ALMG with a generated 48-row
  classifier dataset and a local checkpoint containing one completed candidate.
  Selected the run and explicitly approved immediate training in the desktop UI.
  The run reused that candidate and reached preview at held-out macro F1 1.000.
  Opened the native run record and verified state resumed, restored_candidates 1,
  compatibility key, source SHA-256 and final SHA-256 matching the checkpoint file.
  All fixture artifacts stayed outside Git; no external collection occurred.
- Verification: 204 Python tests (203 passed, one opt-in Metal test skipped), all
  16 Flutter tests passed and Flutter analysis clean. Tests verify resume skips
  completed fits and matches uninterrupted evaluation, changed-dataset rejection,
  and corrupt-checkpoint rejection followed by successful replacement.
- Remaining: from-scratch decoder registration/construction, explicit approach
  selection, complete versioned pipeline interfaces and language-model-specific
  checkpoint lineage. P3-LMF-01 stays open; physical power/Windows blockers remain
  separate and do not block independent implementation.

P3-LMF-01 partial progress · registered decoder initialization · 2026-11-19:
- Added a bounded NumPy CPU decoder-only Transformer constructor with token and
  positional embeddings, causal self-attention, residuals, layer normalization,
  feed-forward block and output head. Weights come solely from a local seeded RNG;
  its configuration interface accepts dimensions/seed and rejects pretrained-weight
  inputs. No files, downloads or user weights are read by construction.
- The existing recipe registry now supports validated initializer callbacks.
  Registered decoder_from_scratch version 1 as initialization_only, with a NumPy
  dependency check. Existing classifier/image training catalogs remain unchanged;
  the planner cannot select this incomplete capability for training. Recipe details
  provides an explicit optional CPU initialization check with a result dialog.
  The backend release package includes the constructor module.
- Local app verification: rebuilt/launched macOS ALMG with isolated generated
  fixtures, opened recipe details and clicked Check decoder initialization.
  The native dialog reported passed, newly_initialized, pretrained_weights_loaded
  false, CPU, seed 7, 896 parameters, logits shape 1×4×16, deterministic true and
  causal-prefix error 0.0. No external collection or generated artifacts in Git.
- Verification: 208 Python tests (207 passed, one opt-in Metal test skipped), all
  16 Flutter tests passed, Flutter analysis clean. Tests cover no-file construction,
  same/different seeds, preserved global RNG, causal masking, bounded dimensions
  and token inputs, missing dependency/initializer failures, training-catalog
  exclusion and explicit runtime confirmation. Existing recipes remain covered.
- Remaining: planner discovery of a fully executable from-scratch training recipe,
  explicit approach selection, dataset/tokenizer/pretraining/evaluation/export and
  inference stage integration and full acceptance verification. P3-LMF-01 remains
  open; this delivers construction only and does not enable student training.

P3-LMF-01 partial progress · full-parameter decoder training check · 2026-11-19:
- Added an optional, versioned pretraining fixture that constructs the registered
  decoder from a local seed and trains all 704 parameters on generated four-token
  cycles using MLX/Metal. All nine parameter groups update; no student parameter
  is frozen and no pretrained weights, downloads or external data are used.
  The check evaluates longer held-out sequences, autoregressive generation,
  causal masking and transfer of trained weights to the registered NumPy CPU
  inference implementation. It runs on the existing dedicated inference worker.
- Recipe details exposes explicit Check from-scratch decoder training on macOS.
  Unsupported hardware returns an actionable error before construction; MLX is
  imported lazily. The release package includes the new optional module. This is
  a bounded local verification capability, not planner-enabled user pretraining.
- Local app verification: rebuilt/launched macOS ALMG with isolated fixtures,
  opened recipe details and clicked the training check. Native result dialog:
  newly initialized weights, no pretrained weights, Metal GPU, 100 steps at
  learning rate 0.05, 704 trainable/0 frozen parameters, all nine groups updated;
  loss 1.372652 to 0.067307; held-out next-token accuracy 1.000 on length-12
  sequences versus length-8 training; generated 0,1,2,3 repeated three times;
  causal-prefix error 0; CPU/Metal inference difference 4.28e-7. No artifacts
  or weights were committed and no external collection occurred.
- Verification: all 211 Python tests passed with ALMG_METAL_TESTS=1, including
  actual decoder training and the existing LoRA Metal check; all 16 Flutter tests
  passed; Flutter analysis clean. Tests also cover confirmation and unsupported
  hardware failure before model initialization.
- Remaining: planner-enabled from-scratch workflow and approach confirmation,
  user dataset/tokenizer integration, persistent training/checkpoint lifecycle,
  evaluation/release gates and full versioned stage/manifest integration.
  P3-LMF-01 remains open; blocked physical power and Windows criteria stay separate.

P3-LMF-01 partial progress · decoder artifact roundtrip · 2026-11-19:
- Added version-1 almg-decoder-v1 local JSON persistence for decoder configuration
  and parameters. Loading validates schema, bounded configuration, exact tensor
  names/shapes, finite float32-compatible values and a 4 MiB read limit. It uses
  no executable serialization. Saving validates before writing and atomically
  replaces the destination; failed writes remove staging files and preserve an
  existing artifact. Existing jobs and model formats are unchanged.
- The optional from-scratch training check now saves its trained decoder in a
  temporary directory, reloads it into CPU inference and verifies identical
  held-out predictions. It reports artifact format/size and reload error, then
  removes the temporary artifact. General user-model export/release remains gated.
- Local app verification: rebuilt/launched macOS ALMG with isolated generated
  fixtures; opened recipe details and explicitly ran the decoder training check.
  Native result reported almg-decoder-v1, 16,233 bytes, artifact reload error 0.0,
  temporary_artifact_removed true, and held-out accuracy 1.000. The training check
  still constructs new weights and uses no downloads or external collection.
- Verification: all 215 Python tests passed with ALMG_METAL_TESTS=1, including
  trained-model roundtrip on Metal; all 16 Flutter tests passed. New tests cover
  CPU prediction preservation, malformed versions/config/shapes/tensor names,
  nonfinite or oversized artifacts, invalid-save preservation and failed-replace
  cleanup. Generated artifacts and weights remain outside Git.
- Remaining: planner-enabled workflow/approach confirmation, user dataset and
  tokenizer integration, persistent approved training/checkpoint lifecycle,
  evaluated release integration and complete stage/manifest contracts. P3-LMF-01
  stays open; physical power and Windows verification remain separate blockers.

P3-LMF-01 partial progress · versioned decoder tokenization stage · 2026-11-19:
- Added a bounded local whitespace tokenizer with fit/encode/decode and version-1
  artifact/restore interfaces, NFC normalization, stable sorted vocabulary and
  canonical fingerprint. Vocabulary is fitted only from training documents;
  evaluation text cannot expand it. Unknown words fail explicitly. Bounds cover
  documents, text length, word length, token count and vocabulary growth.
- The optional decoder training check now starts from generated local text,
  derives model vocabulary size from the tokenizer, encodes training/held-out
  documents separately, decodes generated output and verifies tokenizer artifact
  roundtrip alongside the model artifact. The release package includes this stage.
  This is a small pipeline foundation, not completion of the broader Tokenizer
  Engine or user-dataset training workflow.
- Local app verification: rebuilt/launched macOS ALMG with isolated fixtures,
  opened recipe details and explicitly ran the from-scratch decoder check. Native
  result displayed almg-whitespace-tokenizer-v1, four vocabulary words, training-only
  fit source, four training/four held-out documents, successful artifact roundtrip
  and fingerprint d7b780d3c1821f388225872edabb569787a93ca34d22b937528fd45f77416233.
  Generated text was amber birch cedar dune repeated three times; held-out accuracy
  remained 1.000. All data and temporary artifacts were local; no external collection.
- Verification: all 218 Python tests passed with ALMG_METAL_TESTS=1, including
  actual text-to-decoder training; all 16 Flutter tests passed. New tests cover
  deterministic vocabulary, held-out rejection without refitting, NFC/whitespace
  normalization, artifact restoration, invalid versions and input bounds.
- Remaining: planner-enabled workflow and explicit approach selection, user
  document/dataset integration, full tokenizer capabilities, persistent approved
  training/checkpoint lifecycle and evaluated release/manifest integration.
  P3-LMF-01 remains open; blocked power/Windows verification stays separate.

P3-LMF-01 partial progress · bound decoder pipeline bundles · 2026-11-19:
- Added almg-decoder-bundle-v1 to bind the model and tokenizer to versioned
  architecture/tokenization/pretraining-fixture/artifact stages. Its manifest
  records file hashes, tokenizer fingerprint, model configuration, training-record
  hash, seed/steps/learning rate, training/held-out text hashes, evaluation results,
  MLX/NumPy/Python runtime information and component source hashes.
- Bundle loading checks format/stage versions, fixed file set, model/tokenizer
  hashes, training metadata hash and vocabulary/configuration compatibility before
  returning CPU inference objects. Save stages a complete validated directory,
  refuses existing destinations and cleans up on failure. Existing user artifacts
  and legacy classifier/image formats are unchanged. The release package includes
  the new module; general decoder release remains unavailable.
- Local app verification: rebuilt/launched macOS ALMG with isolated fixtures,
  opened recipe details and explicitly ran from-scratch training. Native result
  displayed almg-decoder-bundle-v1, four version-1 stages, decoder.json and
  tokenizer.json as verified files, successful bundle roundtrip and training-record
  hash. CPU prediction reload error remained 0.0 and held-out accuracy 1.000.
  Temporary bundles were removed; no downloads, external collection or artifacts
  were committed.
- Verification: all 222 Python tests passed with ALMG_METAL_TESTS=1, including
  actual trained bundle roundtrip; all 16 Flutter tests passed. New tests cover
  roundtrip predictions/records, tamper rejection before loading weights, invalid
  versions/file sets, training/tokenizer mismatch, preservation of existing
  destinations and failed-stage cleanup.
- Remaining: planner-enabled workflow and approach confirmation, user dataset
  integration, persistent approved training/checkpoint lifecycle and evaluated
  release integration. P3-LMF-01 remains open; hardware verification blockers stay
  separate and do not prevent independent implementation.

P3-LMF-01 partial progress · decoder SGD checkpoint resume · 2026-11-19:
- Added versioned decoder SGD checkpoint save/load using validated model/tokenizer
  bundles. Checkpoint state binds completed steps to architecture configuration,
  tokenizer fingerprint, training-text hash, total step count, learning rate and
  sgd-v1 optimizer identity. Changed revisions are rejected before continuing
  optimization. State includes manifest/revision hashes for checkpoint lineage;
  invalid progress and unsupported settings fail explicitly. Component fingerprints
  and release packaging include the checkpoint module.
- The optional training check now serializes a step-50 checkpoint, reconstructs
  its weights/state, completes the remaining 50 steps and compares all parameters
  with a separately uninterrupted 100-step run. It uses constant-rate SGD without
  momentum, so no additional optimizer slots are required. Temporary checkpoint
  bundles are removed; general job restart/resume integration is still pending.
- Local app verification: rebuilt/launched macOS ALMG with isolated fixtures,
  opened recipe details and explicitly ran from-scratch decoder training. Native
  result reported almg-decoder-sgd-checkpoint-v1, completed_steps 50, resumed_steps
  50, manifest/revision hashes, uninterrupted parameter difference 1.1921e-7
  (below 1e-6), temporary checkpoint removal and held-out accuracy 1.000.
  No external collection or generated artifacts were committed.
- Verification: all 225 Python tests passed with ALMG_METAL_TESTS=1, including
  actual checkpoint-resumed Metal training; all 16 Flutter tests passed. Tests
  cover exact saved weights/progress, changed text/tokenizer/optimizer/settings
  rejection and invalid progress/settings bounds.
- Remaining: planner-enabled workflow/approach confirmation, user dataset
  integration, durable approved job lifecycle and interruption recovery, evaluated
  release integration and complete acceptance verification. P3-LMF-01 stays open;
  blocked physical power and Windows checks remain separate.

P3-LMF-01 partial progress · durable approved decoder trials · 2026-11-19:
- Added an explicitly approved, asynchronous saved-trial workflow for the bounded
  generated-text decoder pipeline. Version-1 trial records persist approval ID,
  timestamp, from-scratch scope/recipe/component revision, status, errors, result
  and artifact directory under decoder-trials. Workers validate the saved approval
  revision before training. The dedicated inference worker remains the executor.
- Trial training can retain its step-50 checkpoint and validated trained bundle.
  Startup recovery marks stale queued/running trials interrupted and requires
  renewed approval; resume preserves earlier approvals and reuses a matching
  checkpoint. Changed implementation revisions or an existing complete bundle
  cannot be overwritten. Old classifier/image jobs and formats are unchanged.
  The release package includes the new trial module.
- Recipe details now offers Approve and save a local decoder trial and View saved
  decoder trials. History exposes status/result and explicit approval to resume.
  This is a saved generated-text trial, not planner-enabled general pretraining.
- Local app verification: rebuilt/launched macOS ALMG with isolated fixtures.
  Approved a saved trial in the desktop UI; a controlled fixture interruption
  after checkpoint save produced an interrupted record with its approval and
  checkpoint intact. Restarted the backend, reopened the same trial from native
  history and clicked Approve resume. The same ID completed using the saved
  checkpoint, retained its previous approval, recorded a new approval and kept a
  validated bundle at accuracy 1.000. A further fresh desktop-approved trial
  verified the final worker-side approval guard and persisted another valid bundle.
  No external collection occurred; all generated artifacts stayed outside Git.
- Verification: all 232 Python tests passed with ALMG_METAL_TESTS=1, including
  actual interrupted training/checkpoint reuse; all 16 Flutter tests passed;
  Flutter analysis clean. Tests cover confirmation, durable receipts/results,
  restart recovery, renewed approval, revision rejection before training,
  checkpoint preservation, existing-bundle protection and worker failure recovery.
- Remaining: planner discovery and approach selection for a fully integrated
  recipe, user dataset ingestion, scheduling/cancellation controls for general
  decoder jobs, evaluation/release gates and complete acceptance verification.
  P3-LMF-01 stays open; physical power and Windows blockers remain independent.

P3-LMF-01 partial progress · cooperative saved-trial cancellation · 2026-11-19:
- Added explicit cancellation requests for active saved decoder trials. Per-trial
  stop events are checked before initialization, at optimizer-step boundaries and
  before bundle publication. Queued cancellation prevents training when the worker
  reaches that trial. Workers preserve cancellation metadata and serialize final
  state updates with cancellation requests; completed trials cannot be cancelled.
- Cancelled trials use the existing interrupted state with optional cancellation
  fields, retain approvals/checkpoints/artifacts and require renewed approval to
  resume. Resume resets the request flag and preserves earlier approvals. Legacy
  records without cancellation fields remain readable/recoverable; reads do not
  backfill or rewrite their history. Artifact directories are visible for running
  and interrupted trials. General scheduling controls remain future work.
- Local app verification: rebuilt/launched macOS ALMG with an isolated fixture
  paused at its saved step-50 checkpoint. Approved a saved trial, clicked Cancel
  saved decoder trial in its native dialog, and observed interrupted/user_cancelled
  with a valid retained checkpoint and no completed bundle. Clicked Approve resume;
  the same trial ID completed with a new approval, previous approval preserved,
  cancel flag cleared, saved checkpoint reused and held-out accuracy 1.000.
  The resulting saved bundle validated. No external collection occurred.
- Verification: all 237 Python tests passed with ALMG_METAL_TESTS=1, including
  real cancellation at a serialized checkpoint and later resume; all 16 Flutter
  tests passed; Flutter analysis clean. Tests cover queued cancellation without
  trainer invocation, running cancellation and artifact preservation, completed
  trial protection, renewed approval, pre-initialization stop and legacy records.
- Remaining: planner-enabled recipe/approach selection, user dataset integration,
  scheduler/idle/power integration for general decoder jobs, evaluated release
  gates and full acceptance verification. P3-LMF-01 stays open; hardware blockers
  remain independent. Generated artifacts and weights are not committed.

P3-LMF-01 partial progress · reviewed decoder approach proposals · 2026-11-19:
- Added a local-Qwen proposal adapter that recommends from_scratch, fine_tuning,
  distillation or retrieval for a decoder trial goal, validates the response and
  persists a version-1 proposal without starting execution. Only the existing
  generated-local-text from-scratch trial is executable. Unavailable approaches
  can be reviewed but cannot create a trial.
- Proposal IDs/revisions bind goal, recommendation, explanation, fixed scope and
  implementation revision. Execution requires explicit confirmation of the exact
  reviewed revision; changes during planning or between review/approval invalidate
  it. The trial stores the proposal and binds it into its approval receipt. Legacy
  direct-trial approvals retain their existing binding and records remain readable.
- Recipe details now supports goal entry, visible planning progress and an
  approach/scope review. Confirmation is offered only for an executable proposal.
  The goal dialog owns/disposes its controller with its widget lifecycle and has
  keyboard autofocus. Only planning uses the longer local-model response timeout.
- Local app verification: rebuilt/launched macOS ALMG with a deterministic local
  planner fixture. Entered a goal through the native keyboard, requested/reviewed
  from_scratch, verified no trial existed before confirmation, then confirmed.
  The trial completed at accuracy 1.000 with the reviewed proposal bound into its
  receipt. A second retrieval proposal showed an unavailable message and no
  confirmation control; trial count remained one. Actual decoder training used
  Metal. Live Qwen generation was not exercised in this slice. No downloads or
  external collection occurred; generated artifacts remained outside Git.
- Verification: all 241 Python tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. Tests cover no execution before approval,
  exact revision binding, unavailable approaches, stale/during-planning capability
  changes, invalid planner output and goal bounds.
- Remaining: main planner discovery/routing for a fully integrated decoder recipe,
  live-Qwen approach verification, user dataset integration, general scheduling,
  evaluated release gates and full acceptance verification. P3-LMF-01 remains open;
  physical power and Windows blockers remain independent.

P3-LMF-01 partial progress · live Qwen planning and supervisor provenance · 2026-11-19:
- Approach proposals now capture the configured local supervisor model, loaded
  state and a SHA-256 revision of its loaded verification receipt after generation.
  The receipt hash identifies verified model metadata; it is not a new per-request
  hash of the full weight files. Proposal/approval revision binding includes this
  provenance, and the review dialog displays the planner model. Unspecified local
  test callbacks do not silently claim a loaded model identity.
- Local app verification used the actual installed mlx-community/Qwen3.8-27B-4bit
  model with HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1. Rebuilt/launched macOS
  ALMG with isolated generated training fixtures and no planner stub. Qwen
  recommended from_scratch for the tiny new-weights trial, the native review showed
  its model identity, and no training existed before confirmation. After desktop
  confirmation, the trial completed at accuracy 1.000 with the proposal and loaded
  supervisor verification revision bound into its approval record.
- A second real Qwen request recommended retrieval for a local-document/no-training
  goal. ALMG showed the unavailable message with no confirmation control, and trial
  count remained one. Restarted the backend (supervisor initially unloaded) and
  reopened the completed trial from native history; the full saved record and
  original loaded-supervisor provenance were unchanged. This closes the prior
  live-Qwen verification gap for the bounded trial proposal workflow.
- All 44 existing model-directory files retained identical sizes and modification
  times; no weights/downloads were changed. Completed fixture servers created in
  this chat were stopped to free resources, with their files/artifacts preserved.
  No external collection or generated artifacts were committed.
- Verification: all 243 Python tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. New tests cover unloaded identity, stable
  verification-receipt hashing, changed receipt revisions, capture after generation
  and identity inclusion in proposal hashes.
- Remaining: main planner routing for the full decoder recipe, user dataset
  integration, general scheduling and evaluated release gates. P3-LMF-01 stays open;
  physical power and Windows acceptance remain independently unverified.

P3-LMF-01 partial progress · local decoder text-dataset preparation · 2026-11-19:
- Added a versioned preparation interface for 3–16 local UTF-8 text documents,
  bounded to 64 KiB each and 128000 source bytes total. The native picker sends
  original bytes, preserving raw SHA-256 provenance including UTF-8 BOMs; NFC,
  whitespace and leading-BOM normalization are separate preparation steps.
- Normalized exact duplicates share a group and are reported with source names
  and hashes. Unique groups are deterministically partitioned into disjoint train,
  validation and test sets. A bounded tokenizer is fitted only on training text;
  evaluation vocabulary issues are reported without refitting. License status is
  recorded as user-provided/not reviewed. This does not claim full dataset QA.
- Prepared datasets publish immutable documents/tokenizer/manifest artifacts under
  decoder-datasets, with content/file hashes, source metadata, split counts and
  findings. Reading verifies content, partitions and training-only tokenizer
  consistency. Recipe details supports preparation and saved review; preparation
  starts no training or external collection. The release package includes the module.
- Local app verification: rebuilt/launched macOS ALMG and exercised the native
  file picker with local fixtures. Too-small selection was rejected before publish.
  Seven sources produced six unique documents, splits 4/1/1, vocabulary four and
  one duplicate finding. Restarted the backend/app and reopened the identical
  manifest from native history. Final original-byte import of eight sources,
  including BOM/whitespace duplicates, again yielded six groups and two duplicate
  findings; all source hashes matched the selected files, the prior dataset stayed
  unchanged, and no decoder trial was created. Successful retry clears stale errors.
- Verification: all 250 Python tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. New tests cover grouped deduplication,
  split isolation, no evaluation-vocabulary leakage, reproducible reordered input,
  immutable prior versions, byte/BOM provenance, invalid inputs and tamper rejection.
- Remaining: connect reviewed user datasets to approved decoder training, main
  planner routing, general scheduling, evaluated release gates and broader dataset
  engineering. P3-LMF-01 remains open; hardware verification blockers stay separate.
  No generated datasets/artifacts or downloaded weights were committed.

P3-LMF-01 partial progress · approved reviewed-dataset decoder training · 2026-11-19:
- Connected compatible prepared local datasets to a bounded from-scratch decoder
  trial through a separate explicit confirmation. The approval specification binds
  the full reviewed manifest, dataset ID, file hashes and implementation revision.
  Preflight and worker checks reject changed reviews/content, missing tokenizer
  artifacts, evaluation-vocabulary findings, empty/too-short data or trial-size
  limits. Generated-text proposals cannot silently expand into local-dataset scope.
- The local-data stage uses training-only tokenization, document-isolated windows
  of at most 16 inputs, seed 7, width 8, 100 constant-rate SGD steps and immediate
  Metal execution. Limits are 64 training and 32 windows per evaluation split.
  Evaluation reports initial/final loss, separate validation/test next-token
  accuracy, target 0.8 and pass/fail; trial completion does not release a model.
- Preserved step-50 checkpoint/cancellation/resume controls and added versioned
  pretraining_local bundles recording the dataset/review revisions and evaluation.
  CPU inference is checked against Metal output. Existing fixture bundles remain
  readable and their default save/checkpoint call contracts are unchanged. Release
  packaging includes the new lazy-MLX local-data trainer.
- Local app verification: rebuilt/launched macOS ALMG with isolated prepared-text
  fixtures. A vocabulary-incompatible dataset showed no training control and
  created no trial. Reviewed a compatible six-document dataset, observed the
  explicit scope/step/seed confirmation and verified no training before approval.
  After native approval the trial completed with validation and held-out accuracy
  1.000, generated text and a validated pretraining_local bundle bound to that exact
  dataset. Restarted the backend and reopened the unchanged trial/approval/evaluation
  from native history. No external collection occurred or existing data was rewritten.
- Verification: all 255 Python tests passed with ALMG_METAL_TESTS=1, including real
  local-data training and cancellation/checkpoint resume; all 16 Flutter tests
  passed; Flutter analysis clean. Tests cover review binding, quality/scope guards,
  queued data tampering before trainer invocation, valid CPU bundle output and
  serialized local-data checkpoint recovery.
- Remaining: main planner routing and data-aware approach proposals, general
  scheduling/idle/power integration, richer dataset/tokenizer support, evaluated
  release gates and full acceptance verification. P3-LMF-01 remains open; physical
  power and Windows verification remain independent blockers. Generated models,
  datasets and downloaded weights are not committed.

P3-LMF-01 partial progress · dataset-aware local trial proposals · 2026-11-19:
- Added “Plan with reviewed dataset” to compatible prepared dataset reviews.
  The local planner receives the goal, verified dataset ID, document/split counts,
  training-only tokenizer metadata and preparation findings without document text.
  The approach review shows the exact selected corpus and bounded training limits.
- Revalidated data after planning and before approval/execution. Proposal approval
  binds the dataset manifest revision and implementation; omitting or substituting
  the selected dataset fails before queueing. Existing generated-text proposals
  retain their original scope. Unsupported approaches remain non-executable, and
  planning alone creates no trial. Existing direct dataset approvals still work.
- Local app verification: rebuilt/launched macOS ALMG against isolated local
  fixtures; selected the six-document corpus, entered a goal and observed its
  dataset-aware approach review with no trial present before confirmation. Used a
  deterministic local planner fixture (not a new live-Qwen quality evaluation).
  Native confirmation ran actual Metal training: loss 1.365828 → 0.067526,
  validation/test next-token accuracy both 1.000; the completed record retained
  the exact proposal and dataset approval. Reopened native saved history after
  app restart and verified the entire displayed record was unchanged. Evidence:
  /tmp/almg-data-plan-qa/{proposal-ui.txt,completed-ui.json,restarted-ui.json}.
- Verification: 257 Python tests passed with ALMG_METAL_TESTS=1, including actual
  Metal training; 16 Flutter tests passed; Flutter analysis clean. New tests verify
  no document-text disclosure, no execution during planning, dataset substitution
  rejection, correct trainer dispatch and data tampering during planning.
- Remaining: main planner routing, general scheduling/idle/power integration,
  richer data/tokenizers, evaluated release gates and full acceptance verification.
  P3-LMF-01 stays open; physical power and Windows checks remain independent blocked
  items. No external collection, generated artifacts or weights are committed.

P3-LMF-01 partial progress · registered decoder planning capabilities · 2026-11-19:
- Added validated workflow/approach/scope metadata and request-time planning
  discovery to the recipe registry. Decoder metadata now describes the implemented
  bounded local trial, fresh initialization, Metal runtime, private bundles and
  revision-bound checkpoint resume. General job discovery remains limited to the
  existing available classifier/image implementations.
- Decoder planning now receives the registered contract and must return a valid
  registered recipe selection. Missing/unknown/wrong-workflow selections fail
  before any approval or execution. Supported approach/scope metadata determines
  proposal executability; unsupported approaches remain review-only. Persisted
  specifications and proposals bind the complete registry contract, so a contract
  change invalidates stale approval. Native approach review names the recipe.
- Local app verification: rebuilt/launched macOS ALMG with an isolated deterministic
  local planner fixture, observed the registered decoder in approach review and
  verified no trial existed before confirmation. Native confirmation executed real
  Metal training from new weights (no pretrained student weights): 704 trainable
  parameters, loss 1.372652 → 0.067308, held-out accuracy 1.000. Saved proposal and
  execution specification contain identical registered contracts. Reopened saved
  native history after app restart; the full displayed record remained unchanged.
  Evidence: /tmp/almg-registry-plan-qa/{planner-input.json,proposal-ui.txt,
  completed-ui.json,restarted-ui.json}. This is registry plumbing verification,
  not an additional live-Qwen planning-quality evaluation.
- Verification: 259 backend tests passed with ALMG_METAL_TESTS=1, including actual
  Metal runs and existing classifier/image checks; 16 Flutter tests passed;
  Flutter analysis clean. Added invalid capability metadata, isolated catalog
  snapshots, absent/unknown selection and stale contract approval coverage.
- Remaining: general workbench planner routing into the factory, scheduling/idle/
  power integration, richer data/tokenizers, evaluated release gates and full
  acceptance verification. P3-LMF-01 remains open. Physical power and Windows
  verification remain separate blocked criteria; no external collection or
  generated artifacts/weights are committed.

P3-LMF-01 partial progress · automatic workbench factory routing · 2026-11-19:
- Main training-goal selection now includes decoder trial capabilities discovered
  from the registry. A selected factory recipe creates a persisted approach review
  in the existing training conversation, rather than entering classifier planning.
  The native workbench shows the recipe, approach, rationale and generated-text
  scope (fresh weights, 100 steps, seed 7, immediate Metal; no model release).
- Added revision-checked explicit confirmation through the job API. Missing or
  stale consent and unavailable approaches cannot queue a trial. Successful approval
  saves its durable trial ID on the conversation; repeated approval cannot launch
  another trial. The linked view reuses the existing result/cancel/resume controls.
  Factory review/trial states survive restoration, and users can revise the goal.
- Local app verification: rebuilt/launched macOS ALMG with isolated deterministic
  local routing and approach fixtures. Typed a plain-language goal in the main
  conversation and sent it using native keyboard navigation. Observed automatic
  decoder approach review and no trial before confirmation. Native confirmation
  completed actual fresh-weight Metal training with held-out accuracy 1.000;
  opened the linked result and verified its exact proposal matched the conversation.
  Restarted both backend and app, reopened the conversation from native history,
  and verified the entire linked trial record was unchanged. Evidence:
  /tmp/almg-workbench-qa/{routing-input.json,approach-input.json,review-ui.txt,
  completed-ui.json,restarted-ui.json}. Planner fixtures test integration, not
  additional live-Qwen routing quality. No external collection occurred.
- Verification: 261 backend tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. New coverage exercises automatic recipe
  discovery, no implicit training, stale/missing consent, duplicate approval,
  unavailable approaches, saved review restoration and interrupted-trial linkage
  after backend restart. Existing classifier/image planner checks still pass.
- Remaining: automatic integration of reviewed user datasets, general scheduling/
  idle/power integration, richer data/tokenizers, evaluated release gates and full
  acceptance verification. P3-LMF-01 stays open. Physical power and Windows checks
  remain separate blocked criteria. Generated artifacts/weights and unrelated
  user edits are excluded from this commit.

P3-LMF-01 partial progress · reviewed datasets in automatic factory conversations · 2026-11-19:
- Added prepared local dataset selection to the main decoder approach review.
  The native picker fetches the verified manifest, requires explicit review, then
  requests a new asynchronous approach proposal for that exact dataset. The
  conversation shows its dataset ID/count and saved train/validation/test scope.
  Selecting data or asking for a proposal does not start training.
- Backend preflight rejects missing consent, absent/changed manifests and existing
  tokenizer/data incompatibilities before changing the review stage. New proposals
  and the conversation retain the reviewed dataset snapshot; final approval passes
  that snapshot into the durable trial. An earlier generated-text proposal revision
  cannot authorize the data-bound run. Planner failure records failure without
  submitting training; existing generated-text routing uses the same helper.
- Local app verification: rebuilt/launched macOS ALMG against isolated local text
  fixtures. Seeded a factory-review conversation through the local API after native
  goal-input accessibility proved unreliable, then exercised the changed workflow
  entirely in the native app: selected six-document data, reviewed its manifest,
  requested a fresh proposal, verified exact corpus scope and no trial before final
  confirmation, approved, and opened the linked completed result. Actual Metal
  training reduced loss 1.365828 → 0.067526 with validation/test accuracy 1.000.
  Planner input contained dataset metadata and no fixture document text. Restarted
  backend and app, reopened the saved conversation and verified its linked result
  (dataset/proposal/approval/metrics) was unchanged. Deterministic planner fixtures
  verify integration rather than additional live-Qwen planning quality. Evidence:
  /tmp/almg-factory-data-qa/{dataset-review-ui.json,proposal-review-ui.txt,
  completed-ui.json,restarted-ui.json}.
- Verification: 263 backend tests passed with ALMG_METAL_TESTS=1; 16 Flutter tests
  passed; Flutter analysis clean. New tests cover reviewed data consent, invalid
  manifests, asynchronous proposal staging, stale earlier approval rejection,
  correct dataset linkage, restore and planning failure without training.
- Remaining: general scheduling/idle/power integration, richer data/tokenizers,
  evaluated release gates and full acceptance verification. P3-LMF-01 remains open;
  physical power and Windows checks remain independent blocked items. No external
  collection occurred; generated artifacts/weights and unrelated edits are excluded.

P3-LMF-01 partial progress · guarded idle/AC decoder execution · 2026-11-19:
- Added an explicit opt-in idle/AC guard to main decoder approval. Approval saves
  the policy and enters durable waiting_idle without occupying the Metal worker.
  A cancellable waiter submits training only when the existing local probe confirms
  AC power and at least 600 idle seconds. Unknown/failed probes remain waiting.
  Waiting accommodates the user activity caused by clicking approval itself.
- Guarded training rechecks readiness through existing training-boundary callbacks.
  Readiness loss interrupts with a distinct reason, preserves completed checkpoints
  and requires renewed explicit resume approval. Resume retains the saved policy;
  callers cannot silently disable it. Policy participates in approval revision
  binding. Waiting is cancellable and restart recovery never starts it implicitly.
  Immediate legacy trials retain their original approval representation/behavior.
- Local app verification: rebuilt/launched macOS ALMG with isolated synthetic
  readiness fixtures and a seeded factory-review conversation. Native opt-in and
  confirmation produced waiting_idle while unready, with no model artifacts. After
  fixture readiness changed, actual Metal training began; readiness loss following
  step-50 checkpoint creation interrupted the run with checkpoint preserved. Native
  resume approval after restored readiness reused that checkpoint, retained the
  guard, created a new approval and completed with held-out accuracy 1.000.
  Restarted backend/app and reopened the linked native result; the entire saved
  policy, approval history and completed result were unchanged. Final evidence:
  /tmp/almg-readiness-final-qa/{waiting-ui.json,paused-ui.json,completed-ui.json,
  restarted-ui.json}. Synthetic probes verify control flow, not physical power
  transitions or real ten-minute idle behavior; those acceptance checks stay open.
- Verification: 268 backend tests passed with ALMG_METAL_TESTS=1; 16 Flutter tests
  passed; Flutter analysis clean. Added waiting without worker occupation, invalid
  probes, cancellation, restart recovery, approval-policy binding, worker failure,
  boundary interruption and real Metal checkpoint-resume coverage.
- Remaining: broader resource scheduling and physical idle/power/sleep verification,
  richer data/tokenizers, evaluated release gates and full acceptance verification.
  P3-LMF-01 remains open. Unavailable Windows/physical checks remain independent
  blocked criteria; no external collection, generated artifacts or weights are
  committed, and unrelated user edits are preserved.

P3-LMF-01 partial progress · decoder memory/disk admission and worker checks · 2026-11-19:
- Connected bounded decoder approvals to the existing local memory/disk reserve
  checks. Added a validated byte-budget entry point shared with classifier/image
  checks, retaining their existing reserve calculations. Decoder specification
  records a versioned conservative 128000-byte import budget and resource-checker
  source revision; approval binds that budget. Minimum estimates are 256 MiB plus
  eight times the data budget for memory and 64 MiB plus four times for disk.
- Admission rejects low/unknown resources before persisting a new trial or queueing
  work. Worker entry rechecks after queue/idle waiting and before model construction;
  loss interrupts with resources_unavailable and requires explicit approval to
  resume. Completed checkpoints and prior records remain intact on failure. Saved
  trials retain bounded timestamped admission/execution resource evidence, including
  available values and estimated reserves. These are estimates, not peak guarantees.
- Local app verification: rebuilt/launched macOS ALMG with an isolated seeded
  conversation and synthetic low-memory/disk fixtures. Native low-memory approval
  failed without creating a trial. Restored real resource probes, opted into idle
  waiting and verified saved admission evidence with no model artifacts. Simulated
  disk loss before readiness admission; the native linked trial showed resource
  interruption before model initialization. Restored actual memory/disk probes and
  approved resume natively: real Metal training completed with held-out accuracy
  1.000 and recorded admission/admission/execution checks. Restarted backend/app,
  reopened the linked result and verified its full record was unchanged. Evidence:
  /tmp/almg-resource-qa/{low-memory-ui.txt,waiting-ui.json,low-disk-ui.json,
  completed-ui.json,restarted-ui.json}. Resource faults/readiness were synthetic;
  no external collection or disruptive physical resource stress was performed.
- Verification: 272 backend tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. New tests cover low memory/disk, unavailable
  probes, loss after waiting, checkpoint preservation, failed resume preserving the
  prior record, successful resource evidence and approval-bound budget validation.
- Remaining: resource monitoring during optimization, physical power/sleep/idle
  verification, richer data/tokenizers, evaluated release gates and full acceptance.
  P3-LMF-01 stays open; independent physical/Windows blockers remain skipped.
  Generated artifacts, downloaded weights and unrelated user changes are excluded.

P3-LMF-01 partial progress · resource monitoring during decoder optimization · 2026-11-19:
- Extended the shared decoder stop callback to probe memory/disk reserves at every
  existing cooperative training boundary, including optimizer steps and the final
  pre-publication check. The same callback serves generated and reviewed-data
  trials. Low/unknown resources interrupt rather than continuing optimization;
  completed checkpoints remain available for explicit approval-bound resume.
- Persisted a bounded version-1 monitoring summary: successful-boundary count,
  latest successful resource snapshot and timestamped last failure. Kept admission/
  execution evidence separately. Evidence writes merge the current durable record
  under the trial lock, retaining concurrent cancellation flags; cancellation is
  checked again after probing. Historical failure evidence survives successful
  resume rather than being erased by later successful probes.
- Local app verification: rebuilt/launched macOS ALMG with an isolated seeded
  review and synthetic memory-loss fixture triggered after actual step-50 checkpoint
  creation. Native approval ran real Metal training, then the linked result showed
  resources_unavailable, 151 successful boundary checks, recorded low-memory
  evidence and an intact checkpoint. Restored actual resource probes and approved
  resume natively: the run reused its checkpoint, completed with held-out accuracy
  1.000, retained the prior failure and recorded 303 cumulative successful checks.
  Restarted backend/app and reopened the linked native result; the entire saved
  record was unchanged. Evidence: /tmp/almg-boundary-resource-qa/{paused-ui.json,
  completed-ui.json,restarted-ui.json}. Resource loss was simulated without stressing
  the machine or claiming physical power/sleep verification.
- Verification: 274 backend tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. Added optimizer-boundary resource failure,
  bounded evidence, preserved checkpoint and concurrent cancellation merge coverage.
- Remaining: physical power/sleep/idle verification, richer data/tokenizers,
  evaluated release gates and full acceptance verification. P3-LMF-01 remains open;
  physical/Windows blockers stay separate and skipped. No external collection,
  generated artifacts, downloaded weights or unrelated user edits are committed.

P3-LMF-01 partial progress · versioned private decoder inference · 2026-11-19:
- Added native prompt-based preview for completed private decoder trials, through
  a confirmed local API. Inference loads and validates the saved model/tokenizer
  bundle from the derived trial path (not a stored arbitrary artifact path), uses
  CPU greedy decoding and never changes release status or weights. Initial prompts
  must fit the saved context and vocabulary; generation uses a sliding context
  and is bounded to 1–32 new tokens (12 in the native UI).
- Added version-1 inference receipts with prompt/output/token IDs, algorithm/runtime,
  context policy, implementation digest and verified bundle-manifest digest. Keeps
  at most 20 private previews on the durable trial; immutable bundle files and
  existing approval/results are preserved. Missing consent, incomplete trials,
  invalid bounds, unknown words, corrupted bundles and nonfinite scores fail
  without recording a successful preview. No tokenizer refitting occurs.
- Local app verification: rebuilt/launched macOS ALMG using an isolated copy of an
  existing actual Metal-trained bundle. Opened its linked result and native preview,
  entered “cedar dune” and approved local generation. The app generated the expected
  12-token continuation “amber birch cedar dune” repeated three times on CPU and
  saved a matching versioned receipt. Native “unseen_word” input was rejected with
  no added history. Verified all bundle file hashes unchanged. Restarted backend/
  app, reopened the linked trial and verified its full record/preview history and
  bundle hashes were unchanged. Evidence: /tmp/almg-inference-qa/{preview-ui.json,
  invalid-prompt-ui.txt,restarted-ui.json,bundle-before.json}. No new external
  collection, pretrained student loading or model release occurred.
- Verification: 278 backend tests passed with ALMG_METAL_TESTS=1; 16 Flutter tests
  passed; Flutter analysis clean. New coverage verifies context sliding, deterministic
  CPU output, consent/state/bounds, corruption/nonfinite-score rejection, bounded
  history, API dispatch, immutable artifacts and retention of existing approval.
- Remaining: physical power/sleep/idle verification, richer data/tokenizers,
  evaluated release/post-training contracts and full acceptance verification.
  P3-LMF-01 remains open; independent physical/Windows blockers remain skipped.
  Generated models, private preview data, downloaded weights and unrelated edits
  are excluded from this commit.

P3-LMF-01 partial progress · optional versioned UTF-8 byte tokenization · 2026-11-19:
- Added an explicit native word/UTF-8-byte tokenizer choice during local text
  preparation. Existing callers default to the unchanged word format. The byte
  format uses a fixed 256-value alphabet, NFC/UTF-8 encoding, bounded documents and
  a training-document revision; it never refits a vocabulary on evaluation text.
  Arbitrary generated byte sequences decode with the artifact's explicit replacement
  policy. The existing plain-text normalization/import and trial-size limits remain.
- Added strict byte artifact restoration through the shared tokenizer interface,
  so prepared datasets, checkpoint/bundle loading, Metal pretraining and CPU private
  inference use the selected format. Dataset verification refits only provenance
  using the restored tokenizer type and checks format/fingerprint against training
  partitions. Legacy word datasets/bundles remain readable and unchanged.
- Local app verification: rebuilt/launched macOS ALMG, selected six actual fixture
  files through the native picker, chose UTF-8 bytes and observed a saved 256-token
  manifest with no evaluation-word vocabulary findings. Native approved training
  on that corpus completed but correctly reported 69.05% validation/test accuracy
  below its 80% target; this private failed evaluation remains saved. Prepared a
  separate simpler repeated-pattern fixture through the local API, reviewed and
  approved it natively, and verified real Metal training passed: validation 97.09%,
  test 97.06%, loss 5.526686 → 0.314144. Native CPU preview accepted unseen “zz”
  and generated 12 tokens using its saved byte artifact. No release occurred.
  Restarted backend/app, reopened native trial history and verified the full
  passing trial/preview unchanged; both byte and legacy word datasets reopened.
  Evidence: /tmp/almg-byte-qa/{dataset-ui.json,training-ui.json,
  positive-training-ui.json,preview-ui.json,restarted-ui.json}.
- Verification: 281 backend tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. Added multilingual/NFC round trips, unseen
  words, invalid byte rendering, bounds/version validation, training-only provenance,
  tampering rejection, disjoint preparation, byte bundle reload and word coexistence.
- Remaining: larger/subword tokenizers and broader dataset engineering, model-quality
  improvements beyond these bounded fixtures, physical power/sleep/idle checks,
  evaluated release/post-training contracts and full acceptance. P3-LMF-01 stays
  open; physical/Windows blockers remain skipped. Generated data/artifacts, downloaded
  weights and unrelated user edits are excluded from this commit.

P3-LMF-01 partial progress · versioned saved-decoder re-evaluation · 2026-11-19:
- Added explicit native/API re-evaluation for completed reviewed-local-data trials.
  Verifies immutable dataset files, saved partitions, bundle integrity, dataset/
  review revisions and tokenizer binding before computing metrics. Recomputes
  train/validation/test next-token accuracy and stable cross-entropy on CPU; reports
  evaluated token/window counts. It does not trust a saved “passed” flag. Version-1
  pass criteria retain 80% validation/test accuracy plus loss below the recorded
  valid initial-training baseline. Invalid scores or missing bindings fail closed.
- Saves at most 20 versioned private evaluation receipts with bundle/dataset/tokenizer
  digests, implementation revision, runtime, target and recomputed metrics. Original
  training results, approvals, status and artifact bytes remain unchanged. This
  adds an evaluation interface, not a model-release or post-training capability.
- Local app verification: rebuilt/launched macOS ALMG with isolated copies of the
  actual Metal-trained byte models from the preceding slice. Natively approved
  re-evaluation of the passing model; independent CPU validation/test accuracy
  matched training (97.09%/97.06%) with token counts and cross-entropy recorded.
  Re-evaluated the below-target model natively and correctly retained a failed
  outcome at 69.05% against the 80% target. Verified both bundles unchanged.
  Restarted backend/app, reopened native evaluation history and verified receipts
  persisted while both original training results and approvals stayed identical.
  Evidence: /tmp/almg-evaluation-qa/{passing-ui.json,below-target-ui.json,
  restarted-ui.json,bundles-before.json}. No external collection or release occurred.
- Verification: 284 backend tests passed with ALMG_METAL_TESTS=1; 16 Flutter tests
  passed; Flutter analysis clean. New tests prove metric recomputation rather than
  trusting earlier success, word/byte support, consent/state checks, binding and
  corruption guards, nonfinite rejection, immutable bundles and bounded history.
- Remaining: evaluated release/post-training/export contracts, larger tokenizers
  and broader data/model-quality work, physical power/sleep/idle verification and
  full acceptance. P3-LMF-01 remains open; independent physical/Windows blockers
  stay skipped. Generated/private artifacts, downloaded weights and unrelated user
  edits are excluded from this commit.

P3-LMF-01 partial progress · approved versioned private decoder export · 2026-11-19:
- Added a two-phase private export review and native local Save workflow for
  reviewed-local-data decoders. Requires saved independent passing evaluation and
  preview receipts bound to the exact bundle/dataset. Fresh CPU evaluation and
  preview reproduction verify those receipts before review and again before write;
  forged/stale metrics, preview output, file hashes or approval revisions fail closed.
  Review binds exact files, receipt revisions and export implementation digest.
- Version-1 ZIP contains fixed model/tokenizer/bundle-manifest members plus an
  export manifest carrying provenance, approved review and quality receipts. Dataset
  documents are excluded; native review explicitly discloses preview prompt content.
  Artifacts publish into new immutable export directories with archive-hash receipts
  and bounded trial history. Existing bundle bytes, approvals and private trial status
  stay unchanged. No public registry/release or external transfer is enabled.
- Local app verification: rebuilt/launched macOS ALMG against isolated copies of
  the previously evaluated actual Metal-trained models. Natively reviewed the passing
  model's exact export, verified no archive before approval, approved and selected
  /tmp/almg-export-qa through the native Save dialog. The app saved a 49,160-byte
  ZIP; inspected its exact four members, verified hashes/review/receipt binding,
  extracted it and loaded the byte-tokenized bundle successfully. Natively attempted
  the below-target model and observed rejection before export; only the authorized
  passing-model archive existed. Restarted backend/app and reopened native history;
  the full export ledger and saved archive hash were unchanged, with private status
  retained. Evidence: /tmp/almg-export-qa/{review-ui.json,saved-ui.txt,rejected-ui.txt,
  restarted-ui.json,decoder-private-0ee2f1bd.zip}. No external collection occurred.
- Verification: 287 backend tests passed with ALMG_METAL_TESTS=1; 16 Flutter tests
  passed; Flutter analysis clean. New tests cover explicit/exact approval, independently
  reproduced gates, stale/altered receipts, bundle tampering, fixed archive members,
  post-extraction bundle validation, no dataset documents and immutable source files.
- Remaining: public release/import/registry and post-training contracts, broader
  data/tokenizer/model-quality work, physical power/sleep/idle checks and full
  acceptance. P3-LMF-01 remains open; independent physical/Windows blockers stay
  skipped. Generated exports/private artifacts, downloaded weights and unrelated
  user edits are excluded from this commit.

P3-LMF-01 partial progress · isolated private decoder archive import · 2026-11-19:
- Added confirmed native ZIP import into a separate immutable decoder-imports
  namespace with a persistent private inventory and CPU prompt preview. Shared the
  bounded inference implementation with existing trial previews. Import never creates
  a training job, resume checkpoint or public release; imported IDs cannot be used
  with trial training/export APIs. Dataset documents remain excluded, so evaluation
  claims are explicitly marked not independently re-evaluated and cannot be relabeled
  as verified through import metadata.
- Validates the exact four archive members, bounded archive/member sizes, supported
  compression, regular-file entries, export review/receipt/file hashes and the saved
  bundle/tokenizer formats before publishing a new copy. Rejects traversal/extra
  members, symlinks, oversized payloads, corrupt provenance and changed weights.
  Preview rechecks bundle/provenance integrity and retains at most 20 local receipts.
  Existing word/byte trial preview behavior remains compatible.
- Local app verification: rebuilt/launched macOS ALMG with isolated fixtures, chose
  the actual ZIP saved in the preceding export slice through the native file picker,
  reviewed and confirmed import, and observed its separate private-only inventory
  record with an exact archive hash and byte tokenizer. Native “zz” preview matched
  pre-export output (“a a a a a a ”). Natively attempted a deliberately changed model
  ZIP and observed hash/provenance rejection with no second or partial import and
  no change to the valid record. Restarted backend/app, reopened imported-model
  inventory and verified the full import/preview record was unchanged; no decoder
  training namespace existed. Evidence: /tmp/almg-import-qa/{imported-ui.json,
  preview-ui.json,rejected-ui.txt,restarted-ui.json}. No external collection occurred.
- Verification: 290 backend tests passed with ALMG_METAL_TESTS=1; all 16 Flutter
  tests passed; Flutter analysis clean. Added strict import/consent, archive safety,
  separate identities, isolated preview/history, false quality-promotion rejection,
  artifact/provenance tampering and trial API separation coverage.
- Remaining: public release/registry and post-training contracts, broader data/
  tokenizer/model-quality support, physical power/sleep/idle checks and full
  acceptance. P3-LMF-01 remains open; physical/Windows blockers stay skipped.
  Generated/private archives, imported models, downloaded weights and unrelated
  user edits are excluded from this commit.

P3-LMF-01 partial progress · private decoder inventory in Model Library · 2026-11-19:
- Added a separate private_imports collection to the existing models API, preserving
  the candidate/release models list. Private rows verify bundle/provenance integrity
  and remain explicitly private CPU previews with unverified evaluation claims.
  Missing/corrupt bundles remain unavailable with re-import guidance; they do not
  become candidates/releases or training jobs. Model Library search/navigation now
  includes these rows while retaining existing classifier/image handling.
- Added a dedicated private preview page with tokenizer/context guidance, explicit
  local generation, saved preview history, integrity errors and disabled inference
  until the import loads successfully. No training/release controls are exposed.
  Added a reusable desktop JSON client with explicit UTF-8 byte Content-Length,
  verified by a real loopback HTTP test, for the library's new POST preview path.
- Local app verification: rebuilt/launched macOS ALMG using an isolated copy of an
  imported actual trained bundle. Opened Model Library directly from Dashboard,
  observed private/unverified labels, opened its preview page and generated expected
  “a a a a a a ” output from “zz”; history persisted. Changed only the isolated model
  file and observed the open page reject inference without adding history. A cold
  native library load showed the corrupt entry as unavailable and disabled. Restored
  exact bytes, restarted backend/app, opened the model from Library again and
  verified healthy access plus unchanged saved preview history and private scope.
  Native verification caught request framing during development; the corrected
  build and actual-wire regression test passed before commit. Evidence:
  /tmp/almg-private-library-qa/{library-ui.txt,preview-ui.txt,
  integrity-error-ui.txt,unavailable-ui.txt,restarted-ui.txt}.
- Verification: 292 backend tests passed with ALMG_METAL_TESTS=1; all 19 Flutter
  tests passed; Flutter analysis clean. Added private inventory/legacy API compatibility,
  corrupt-row handling, preview-only UI, initial integrity failure disabling inference,
  confirmed request scope/history and actual UTF-8 authorization/body framing coverage.
- Remaining: public release/registry and post-training contracts, broader data/
  tokenizer/model-quality support, physical power/sleep/idle checks and full
  acceptance. P3-LMF-01 remains open; physical/Windows blockers remain skipped.
  No external collection occurred. Imported/generated models, downloaded weights
  and unrelated user edits are excluded from this commit.

P3-LMF-01 architecture acceptance complete · versioned stage contracts and saved record · 2026-11-19:
- [x] P3-LMF-01 — Language Model Factory architecture, for the documented bounded
  decoder foundation. Larger-scale dataset/tokenizer work, optional post-training
  algorithms and public release remain in their respective downstream roadmap items.
- Added and validated all eight versioned interfaces: dataset preparation,
  tokenization, fresh architecture, pretraining, evaluation, optional post-training,
  private export and inference. Current post-training explicitly selects version-1
  mode none; unsupported modes/configurations fail before queueing or model loading.
  New bundles store the contract and selected policy. Legacy bundles remain readable;
  derived legacy snapshots are labeled and never rewrite original artifacts.
- Added confirmed “Save and inspect pipeline manifest” in the native saved-trial
  view. The stored version-1 snapshot binds the saved approval/specification, stage
  interfaces, dataset revision, implementation digests, runtime/seed/optimizer data,
  verified bundle/checkpoint manifests and existing evaluation/preview/export history.
  It checks integrity and approval binding and does not change training/release state.
- Acceptance evidence:
  - [x] Registered from-scratch recipe discovered through request-time registry
    metadata. Native planner fixture captured the registered eight-stage contract,
    produced a from-scratch proposal, and required confirmation before a trial existed.
  - [x] Backend recipe/dependency validation and unavailable-alternative rejection
    pass registry/planner tests, including invalid versions, missing dependencies,
    initializer configuration and unsupported post-training policies.
  - [x] Fresh construction without pretrained student weights verified by CPU
    initializer tests and actual native Metal training: all parameters trainable,
    newly_initialized origin, pretrained_weights_loaded false and held-out accuracy
    1.000 on the local fixture. The supervisor was a deterministic planner fixture
    for this replay; student execution and persistence were real.
  - [x] Existing classifier/image recipes remain functional in the complete local
    recipe/execution/planner regression suite and retain their existing dispatch.
  - [x] Registration, selection, validation/failure and legacy persistence coverage
    pass. Current total: 295 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests;
    Flutter analysis clean.
- Local app verification: rebuilt/launched ALMG, chose the saved approach in Training,
  confirmed it, completed real fresh-weight training and saved/inspected the unified
  record. Verified eight interfaces, skipped post-training, bound approval, bundle
  and step-50 checkpoint hashes. Restarted backend/app and reopened the snapshot;
  its complete contents and revision were unchanged. Evidence:
  /tmp/almg-pipeline-qa/{approach-ui.txt,trial-ui.json,manifest-ui.json,
  restarted-manifest-ui.json}, plus the trial's stored pipeline-record.json.
- Next independent Language Model Factory requirement: P3-LMF-02 dataset engineering.
  Physical power/sleep/idle and Windows verification remain open independent blockers.
  No external collection occurred; generated records/artifacts, downloaded weights
  and unrelated user edits are excluded from this commit.

P3-LMF-02 partial progress · immutable local dataset quality audits · 2026-11-19:
- [ ] P3-LMF-02 remains open. Added explicit native “Analyze local text quality”
  and “View saved quality audits” actions for prepared decoder text datasets.
- Version-1 report-only audits use deterministic five-word shingle Jaccard
  similarity (threshold 0.8, minimum 12 words). Findings identify both affected
  source names, original source hashes, normalized groups and saved partitions;
  cross-split matches are labeled potential evaluation contamination. Short
  documents are identified separately; record summaries retain license status.
- Audit receipts bind the dataset/manifest and implementation hashes, are saved
  outside the original dataset under immutable content revisions, and reopen
  without rewriting existing datasets or training approvals. No training starts.
- Local app verification: rebuilt and launched ALMG against an isolated local
  six-document fixture. The native consent action displayed 15 near-duplicate
  pairs, including 9 cross-split pairs. Verified all prepared dataset files stayed
  byte-identical and no decoder trial was created. Restarted ALMG, reopened the
  saved audit from dataset tools and compared the complete displayed receipt:
  contents and revision were identical. Evidence:
  /tmp/almg-audit-qa/{audit-ui.json,restarted-audit-ui.json,before.json}.
- Verification: 299 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and
  clean Flutter analysis. New regression cases cover overlap/provenance,
  deterministic persistence, unrelated/short text, consent, corrupt datasets,
  tampered receipts and preservation of original data.
- Remaining: training-time contamination gates (this slice reports only),
  streaming/incremental/resumable preparation, broader quality/language/PII
  checks, license review, token distributions, mixing and remaining acceptance
  verification. Physical power and Windows blockers remain open and skipped.
  No external collection occurred; generated fixtures/artifacts and unrelated
  user edits are excluded from the commit.

P3-LMF-02 partial progress · pre-training evaluation-overlap admission · 2026-11-19:
- [ ] P3-LMF-02 remains open. Reviewed local decoder datasets now recompute the
  version-1 shingle overlap check from integrity-verified original data before
  planning, trial admission and model construction (including worker/resume
  preflight). Any detected cross-split pair blocks the operation with an affected
  pair count and directions to inspect the local quality audit and prepare
  independent evaluation data. Saved reports cannot bypass the current check.
- Extracted side-effect-free quality computation from audit persistence, retaining
  explicit consent for saving reports. Admission does not rewrite data, audits,
  approvals or checkpoints. Trial specifications now bind decoder_datasets.py
  alongside the existing training implementation hashes. Native approval copy
  explains the evaluation-overlap block.
- Native verification: rebuilt/launched ALMG with isolated local fixtures, reviewed
  the six-document UTF-8-byte dataset and explicitly approved training. ALMG
  displayed “Evaluation contamination check blocked training: 9”; no trial or
  training artifacts were created and original dataset files stayed byte-identical.
  Then approved the zero-detected-overlap control dataset through the same UI:
  real Metal training completed, final train loss 0.067526, validation/held-out
  accuracy 1.000. Only the clean trial c0a6664d380d44ac9e177069e6c8bdb3 was saved.
  Evidence: /tmp/almg-contamination-qa/{blocked-ui.txt,clean-trial-ui.json,before.json}.
- Validation: 301 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests, clean
  Flutter analysis. New tests prove rejection before planner/queue/model calls,
  immutable inputs, no incidental audit writes and fresh checks despite saved
  audit receipts. Existing clean approval/execution/evaluation tests still pass.
- Scope limit: this is a bounded lexical heuristic (five-word shingles, minimum
  12 words, Jaccard >= 0.8), not comprehensive semantic contamination detection.
  Short documents remain identified by the audit; broader contamination policy,
  streaming/incremental/resumable preparation, language/PII/license/quality and
  token/mixing work remain open. Physical power and Windows blockers stay skipped.
  No external collection, generated artifacts or downloaded weights enter Git.

P3-LMF-02 partial progress · local contact-detail privacy findings · 2026-11-19:
- [ ] P3-LMF-02 remains open. Explicit local dataset audits now identify likely
  ASCII email addresses, international-plus phone numbers and formatted North
  American phone numbers. Findings retain affected record names, source hashes,
  normalized groups/splits and Unicode-codepoint locations in normalized text.
  Matched contact values are not copied into findings or new report fields.
- Version-2 audits declare the version-1 local pattern method, supported formats,
  location convention and heuristic limitations. Saved version-1 audits remain
  readable without rewriting them; the native saved-audit list shows privacy
  counts, defaulting to zero for legacy receipts. Native explanatory text states
  that this action identifies findings without filtering or starting training.
- Native verification: rebuilt/launched ALMG with three local synthetic documents,
  explicitly ran “Analyze local text quality”, and read the displayed report.
  Exactly three locations were identified: one email and two phone numbers across
  two records. The date/version/identifier control was not flagged. Compared each
  location to the prepared text and verified that none of the matched values was
  copied into the report. Original dataset files remained byte-identical and no
  decoder trial was created. Restarted ALMG, selected the saved audit summary
  showing 3 privacy matches, and reopened the identical complete receipt/revision.
  Evidence: /tmp/almg-privacy-qa/{audit-ui.json,restarted-audit-ui.json,before.json}.
- Validation: 303 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. Added tests cover normalized Unicode locations, record/source
  provenance, no copied matched values, unrelated controls, immutable repeatability
  and coexistence with legacy saved audit revisions.
- Remaining: explicit reviewed filtering/derived datasets, broader personal-data
  detection, language/quality/license review, streaming/incremental/resumable
  ingestion, token distribution/mixing and remaining acceptance verification.
  These contact-format heuristics do not guarantee personal-data-free text and
  do not change training admission policy. Physical/Windows blockers stay open
  and skipped. No external collection occurred; generated fixtures/artifacts,
  downloaded weights and unrelated user edits are excluded from this commit.

P3-LMF-02 partial progress · reviewed contact filtering into derived versions · 2026-11-19:
- [ ] P3-LMF-02 remains open. Native quality audits with contact findings now offer
  “Create redacted dataset version”, followed by a separate confirmation showing
  replacement count and explaining preservation, repartitioning and fresh review.
  The backend requires literal consent and the current recomputed audit revision;
  stale audits and datasets without detected contacts cannot create a child.
- Detected spans are merged and replaced in reverse order with [CONTACT_REDACTED].
  Preparation atomically publishes a new prepared_for_review dataset, refits the
  same tokenizer kind and recomputes groups/splits. It never starts training or
  transfers approvals. The new optional version-1 derivation binds parent ID and
  manifest hash, audit/method, replacement policy and per-record parent source
  hashes, licenses, groups/splits and replacement counts. Original manifests and
  files stay untouched; existing datasets without derivation remain readable.
- Native verification: rebuilt/launched ALMG with three synthetic local documents,
  ran the current audit, opened redaction confirmation and verified no child
  existed before approval. Explicit confirmation created child dataset
  1a388539ebf443da9126ea56e2524a09 with three replacements and intact parent lineage.
  Verified original files byte-identical, three placeholders in the child, no
  original contact values in child text and no trial created. Audited the child
  through the app: zero detected contact matches. Restarted ALMG and reopened
  the identical child manifest and lineage. Evidence:
  /tmp/almg-redaction-qa/{parent-audit-ui.json,confirmation-ui.txt,
  child-manifest-ui.json,child-audit-ui.json,restarted-child-ui.json,before.json}.
- Validation: 306 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New regression cases cover provenance, byte-tokenizer
  preservation, immutable parents, current-review/consent rejection and safe
  failure when replacements leave fewer than three distinct documents (no
  partially published dataset or temporary preparation folder).
- Remaining: broader PII formats and filtering policies, language/quality/license
  review, streaming/incremental/resumable ingestion, token distributions/mixing,
  export provenance and remaining acceptance checks. Contact heuristics do not
  guarantee personal-data-free text. Physical/Windows blockers remain skipped.
  No external collection occurred; generated data/artifacts, weights and unrelated
  user edits are excluded from this commit.

P3-LMF-02 partial progress · saved-tokenizer distribution analysis · 2026-11-19:
- [ ] P3-LMF-02 remains open. Version-3 local dataset audits report overall and
  train/validation/test token counts, known/unknown occurrences and coverage,
  observed vocabulary, document-length minimum/maximum/mean/median, known-token
  Shannon entropy and the top 20 token IDs/counts with deterministic tie ordering.
  Token text is not copied into the analysis. The method binds the saved tokenizer
  format/hash, never refits on evaluation data, and declares entropy's known-token
  population. Missing or over-limit tokenizers yield explicit unavailability.
- Added a native saved-tokenizer count/unknown summary. Original dataset files,
  tokenizer artifacts, approvals and training state are unchanged. Saved audit
  versions 1 and 2 remain readable without migration or rewriting.
- Native verification: rebuilt/launched ALMG and explicitly audited two local
  fixtures. The UTF-8-byte dataset containing multibyte café text reported 188
  tokens, zero unknowns and exact per-split byte totals; compared all source files
  to their original hashes. The word dataset reported 30 tokens, two unknown
  evaluation words (one per held-out split), zero training unknowns and unchanged
  eight-word training vocabulary. No trial was created. Restarted ALMG and
  reopened the identical complete word-audit receipt and revision. Evidence:
  /tmp/almg-token-stats-qa/{byte-audit-ui.json,byte-summary-ui.txt,
  word-audit-ui.json,restarted-word-ui.json,before.json}.
- Validation: 309 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. Added regression cases verify known/unknown and split totals,
  document lengths, top-ID bounds, multibyte UTF-8 counting, immutable tokenizer,
  missing-tokenizer reporting and coexistence with versions 1/2.
- Remaining: streaming/incremental/resumable ingestion, language/quality/license
  review, broader PII/contamination policy, dataset mixing/sampling, export
  provenance and remaining acceptance verification. Physical/Windows blockers stay
  open and skipped. No external collection occurred; generated fixtures/artifacts,
  downloaded weights and unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · reviewed local dataset export with provenance · 2026-11-19:
- [ ] P3-LMF-02 remains open. Prepared datasets now offer “Review local dataset
  export”, explaining that the private ZIP includes normalized document text and
  source metadata, followed by explicit approval and the native local Save panel.
  Cancellation does not export. No external collection or training occurs, and
  no training approvals are included or transferred.
- A version-1 export receipt binds dataset/manifest revision, exact file hashes
  and sizes, scope and implementation hash. Export revalidates integrity and the
  exact review before returning a bounded deterministic ZIP. Fixed members include
  the original documents.jsonl, manifest.json, optional tokenizer.json and
  dataset-export.json. Original source/license/split and derivation metadata stay
  byte-identical in the manifest. No export staging artifacts or dataset writes
  are created by the backend.
- Native verification: rebuilt/launched ALMG, selected the locally redacted child
  dataset 364a6a9be9954ff9bc5fdf2f23b0b856, inspected the review, approved and saved
  through the macOS file chooser. The app reported “Private dataset ZIP saved”.
  Verified all four archive members and their hashes against the reviewed files;
  the 7,354-byte ZIP retained parent dataset binding, original source provenance,
  licenses and three replacement counts. Restored its controlled dataset members
  into an isolated directory and passed the normal integrity/tokenizer reader with
  an identical manifest. Original dataset files stayed byte-identical; no trial
  was created. Evidence: /tmp/almg-dataset-export-qa/{export-review-ui.json,
  saved-ui.txt,decoder-dataset-364a6a9b.zip,child-before.json,restored/}.
- Validation: 313 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New coverage verifies deterministic archives, exact files and
  provenance roundtrip, consent, stale review/implementation changes, corruption,
  and legacy datasets without tokenizer or derivation metadata.
- Remaining: streaming/incremental/resumable ingestion, language/quality/license
  review, broader PII/contamination policy, dataset mixing/sampling and remaining
  acceptance verification. The export does not add a dataset-import UI. Physical
  and Windows blockers remain open and skipped. Generated ZIPs/fixtures, weights
  and unrelated user edits are excluded from this commit.

P3-LMF-02 partial progress · incremental local dataset versions · 2026-11-19:
- [ ] P3-LMF-02 remains open. Prepared datasets now offer “Add documents to new
  version”, opening the native UTF-8 text picker and a separate confirmation.
  The backend requires literal consent and the unchanged reviewed parent manifest.
  It combines inherited normalized records with approved new original bytes,
  performs the existing exact deduplication and preparation, and atomically
  publishes a new prepared_for_review version. The parent and approvals are not
  rewritten or transferred, and training does not start.
- Version-1 append_local_documents derivation binds the parent ID/manifest hash,
  added-input count, repartition policy and inherited source hashes, licenses,
  groups/splits, including all exact-deduplicated parent source references. New
  inputs retain their original byte hashes. The same tokenizer kind is refitted
  and splits recomputed, requiring fresh review. Existing bounded limits remain:
  at most 16 combined records/inputs, 64 KiB per input and 128000 total bytes.
- Native verification: rebuilt/launched ALMG, selected a saved three-document byte
  dataset, chose addition.txt through the macOS picker and inspected confirmation.
  Verified no child existed before approval. Explicit confirmation created child
  3b6eaef1f1114e6494b0be99fe4b44c9 with four documents, the additional file's original
  BOM/decomposed-Unicode byte hash, preserved inherited provenance and unchanged
  parent files. No trial was created. Restarted ALMG: both versions remained
  selectable and the complete reopened child manifest/lineage was identical.
  Evidence: /tmp/almg-incremental-qa/{confirmation-ui.txt,child-manifest-ui.json,
  restarted-list-ui.txt,restarted-child-ui.json,before.json,addition.txt}.
- Validation: 317 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New cases cover raw-byte hashes, duplicate-source lineage,
  kind preservation, separate versions, consent/stale review, corrupt parents,
  empty/capacity/size failures and absence of partially published datasets.
- Remaining: streaming beyond RAM and interrupted-preparation resume, language/
  quality/license review, broader PII/contamination policies, dataset mixing/
  sampling and remaining acceptance checks. This is bounded incremental ingestion,
  not large-scale streaming or resume support. Physical/Windows blockers remain
  open and skipped. No external collection occurred; generated fixtures/artifacts,
  downloaded weights and unrelated user edits are excluded from this commit.

P3-LMF-02 partial progress · saved local preparation and explicit recovery · 2026-11-19:
- [ ] P3-LMF-02 remains open. Added “Save local preparation draft” with native
  document selection, tokenizer choice and explicit confirmation. A separate
  version-1 draft atomically saves original inputs, content revision and bound
  preparation implementation hashes. Validation uses the existing engine in a
  disposable workspace; saving does not publish a dataset or start training.
- “View saved preparation drafts” reopens pending/completed work after restart.
  Explicit “Prepare saved inputs” verifies snapshot integrity and implementation,
  then atomically publishes to the draft's stable dataset ID. If publication
  succeeds but the completion-record write is interrupted, retry verifies and
  reuses the bound existing output rather than creating another dataset. Completed
  drafts reopen the original dataset. Changed implementations require reselecting
  inputs for a new review; old snapshots are preserved. No automatic resume occurs.
- Native verification: rebuilt/launched ALMG, selected three UTF-8 files (including
  BOM/multibyte text), confirmed a byte-tokenizer draft and compared saved original
  bytes. Draft 6152c39c6bac45e6ba8c8f6b7c2ce2c3 had no published output. Restarted
  both backend and app, reopened the identical pending record, and confirmed
  preparation. A one-shot local fixture interrupted the completion-record write
  after publication, closing the response. Reopened the pending draft through
  the app and confirmed retry: recovered the same verified dataset ID and file
  hashes, with no duplicate publication or changed input snapshot. Completed status
  appeared in the native list; “Open prepared dataset” reopened an identical
  manifest. No training started. Evidence: /tmp/almg-preparation-qa/{draft-ui.json,
  restarted-draft-ui.json,interrupted-ui.txt,published-before.json,
  recovered-dataset-ui.json,completed-draft-ui.json,reopened-dataset-ui.json}.
- Validation: 321 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New cases cover persisted reload/idempotency, interruption
  before preparation and after publication, literal consent, stale implementation,
  corrupt snapshots, invalid inputs and preservation of published files.
- Remaining: streaming beyond RAM and chunk-level large-dataset resume, language/
  quality/license review, broader PII/contamination policy, mixing/sampling and
  remaining acceptance verification. This resumes bounded saved local inputs and
  atomic publication; it does not claim resumable streaming. Physical/Windows
  blockers remain open and skipped. Generated snapshots/artifacts, downloaded
  weights and unrelated user edits are excluded from this commit.

P3-LMF-02 partial progress · transparent per-record text-hygiene scores · 2026-11-19:
- [ ] P3-LMF-02 remains open. Version-4 local audits add a bounded 0–100 hygiene
  score for each affected source record, with word counts, casefolded distinct
  counts, dominant-word share, Unicode letter share and component contributions.
  The report declares version-1 method weights (length 0.5, repetition 0.25,
  letter content 0.25), targets and review threshold 80. Below-threshold findings
  include source hash, normalized group/split and the supporting measurements.
- Native audit text summarizes records needing hygiene review and explicitly says
  scores do not assess meaning or factual accuracy. The method is report-only,
  not a semantic quality measure or training-suitability gate. It does not filter,
  rewrite originals or change training approvals. Audit versions 1–3 stay readable.
- Native verification: rebuilt/launched ALMG with a three-record local fixture,
  explicitly ran the audit and read scores 100.00 for diverse alphabetic text,
  75.00 for a repeated word and 26.56 for the short Unicode café record. The native
  summary identified two records below threshold. Verified original dataset files
  byte-identical and no trial created. Restarted ALMG and reopened the identical
  complete saved receipt/revision. Evidence:
  /tmp/almg-hygiene-qa/{audit-ui.json,summary-ui.txt,restarted-audit-ui.json,before.json}.
- Validation: 322 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New coverage verifies expected scoring order/components,
  Unicode letter handling, affected-record provenance, immutable deterministic
  reporting and coexistence with earlier saved audit versions.
- Remaining: streaming beyond RAM/chunk-level resume, language identification,
  license review, broader quality/PII/contamination policies, dataset mixing/
  sampling and remaining acceptance checks. Word/letter heuristics are not a
  substitute for language-specific or human quality review. Physical/Windows
  blockers stay open and skipped. No external collection occurred; generated
  fixtures/artifacts, weights and unrelated user edits are excluded from Git.

P3-LMF-02 partial progress · optional local document language identification · 2026-11-19:
- [ ] P3-LMF-02 remains open. Added explicit “Identify local document languages”
  and saved-report actions. An optional macOS NaturalLanguage adapter analyzes
  text locally via stdin without a shell, raw-text argv/logging or a remote
  service. Unsupported platforms/provider failures remain explicit unknowns and
  never block preparation, audits or training admission.
- Version-1 immutable reports bind dataset/manifest, source hashes, groups/splits,
  adapter/implementation hashes and OS/runtime. Each record retains up to three
  language candidates/confidences. Identification requires at least 40 alphabetic
  characters, confidence >=0.8 and margin >=0.2; undetermined, short, ambiguous or
  unavailable results stay und/unknown with a reason. Reports estimate a dominant
  document language, not every language in mixed text, and do not change data or
  approvals. Adapter API reference:
  https://developer.apple.com/documentation/naturallanguage/nllanguagerecognizer
- Native verification: rebuilt/launched ALMG and explicitly analyzed three local
  records with the actual installed recognizer. English was identified as en at
  0.996317 and Spanish as es at 0.999268; short café text remained unknown with
  insufficient_alphabetic_text. Provider availability, candidate probabilities
  and source provenance appeared in the native report. Original dataset files
  stayed byte-identical and no trial was created. Restarted ALMG and reopened
  the identical complete report/revision through saved language history. Evidence:
  /tmp/almg-language-qa/{report-ui.json,restarted-report-ui.json,before.json}.
- Validation: 326 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New cases cover consent, provenance, immutable reports,
  ambiguity/undetermined labels, unsupported platforms/provider timeouts, malformed
  candidate output, snapshot/receipt corruption and stdin/no-shell invocation.
- Remaining: streaming beyond RAM/chunk-level resume, license review, dataset
  mixing/sampling, broader language/quality/PII/contamination coverage and remaining
  acceptance checks. The native recognizer is optional, probabilistic and tied to
  the recorded OS version; no cross-platform model dependency was introduced.
  Physical/Windows blockers remain open and skipped. No external collection or
  model download occurred; generated fixtures/artifacts, weights and unrelated
  user edits are excluded from this commit.

P3-LMF-02 partial progress · reviewed local dataset mixing and training weights · 2026-11-19:
- [ ] P3-LMF-02 remains open. Prepared datasets now offer a second-parent selector
  and explicit equal (1:1) or selected-parent emphasis (1:2) review. The bounded
  backend contract accepts two to four distinct, unchanged reviewed parents with
  integer weights 1–4 and at most 16 inherited records before global exact
  deduplication. It preserves parent files, publishes a fresh reviewed version,
  refits the chosen tokenizer kind and recomputes global groups/splits. Parent
  source hashes/licenses/splits and selection weights are retained in derivation.
- Version-1 mixing metadata declares document-window units and training-only
  application. Shared normalized groups sum their selected-parent contributions.
  The trial repeats training windows by those weights; validation/test windows
  remain unweighted. Existing contamination and 64-training/32-evaluation-window
  limits still apply. Invalid/missing/boolean weights and unsupported policies
  reject admission; nested weighted mixtures are explicitly unsupported rather
  than silently losing their weights. Existing datasets default to weight one.
- Saved training results/bundles include effective weights and window counts;
  checkpoint revisions bind the sampling contract as well as data/tokenizer/code.
  No training starts merely by creating a mixture, and approvals do not transfer.
- Native verification: rebuilt/launched ALMG, reviewed two six-record local parents
  and confirmed a 1:2 mixture. Twelve inherited inputs globally deduplicated to
  six groups with effective weight three. Verified 12 training windows versus one
  validation and one test window, unchanged parents and no trial before separate
  approval. Explicit training completed on real Metal: final loss 0.0675263,
  validation/held-out accuracy 1.000. Trial 1c648e7af62b4452ba4d8d20fd1444c0 persisted
  sampling in its result/bundle and bound its checkpoint sampling revision.
  Restarted ALMG and reopened the identical mixture manifest/lineage. Evidence:
  /tmp/almg-mixing-qa/{review-ui.txt,mixture-ui.json,trial-ui.json,
  restarted-mixture-ui.json,parents-before.json}.
- Validation: 330 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New tests cover global deduplication/provenance, training-only
  contributions, unchanged evaluation, stale reviews/consent, kind selection,
  invalid contracts, exact window cap and rejection beyond the cap.
- Remaining: streaming beyond RAM/chunk-level resume, license review, broader
  language/quality/PII/contamination coverage and remaining acceptance checks.
  Physical/Windows blockers remain open and skipped. No external collection
  occurred; generated mixtures/checkpoints, weights and unrelated edits are not
  included in this commit.

P3-LMF-02 partial progress · source permission declarations and exported notes · 2026-11-19:
- [ ] P3-LMF-02 remains open. Prepared datasets now offer a source-by-hash selector,
  user-created / permission-recorded / needs-review bases, a required evidence or
  source note, and explicit confirmation. This records a user assertion, not an
  ALMG permission verification, and does not grant or transfer training approval.
- Version-1 license_declarations bind the exact selected original-byte hash,
  supported basis, note and user_declared status. Recording copies a new immutable
  dataset version with unchanged document/tokenizer bytes, groups, splits and
  sampling metadata. Only matching source license statuses change. The derivation
  binds the parent manifest and retains prior derivation; originals are preserved
  and the new version requires fresh review. Unsupported declarations are rejected
  by the dataset reader; legacy datasets remain readable without rewriting.
- Native export disclosure now includes permission notes. The unchanged private
  export mechanism preserves the new declaration metadata byte-for-byte and
  binds it in the reviewed manifest/file hashes.
- Native verification: rebuilt/launched ALMG, selected doc-0.txt by source hash,
  chose user-created, entered “Created locally for the ALMG permission review
  fixture.” and explicitly confirmed. Child 9abd3b41249f419eae684fc97cec4576 retained
  the exact note and user-declared creation status while original parent files,
  document/tokenizer bytes and saved splits stayed unchanged. No trial was created.
  Reviewed/exported it through the macOS Save panel: the 6,715-byte ZIP retained
  the complete declaration, source hash, evidence note and valid file hashes.
  Restarted ALMG and reopened the identical child manifest and note. Evidence:
  /tmp/almg-permission-qa/{child-ui.json,export-review-ui.json,saved-ui.txt,
  decoder-dataset-9abd3b41.zip,restarted-child-ui.json,before.json}.
- Validation: 334 Python tests with ALMG_METAL_TESTS=1, 19 Flutter tests and clean
  Flutter analysis. New coverage verifies immutable bytes, exact source scope,
  duplicate-hash handling, chained reviews, exported notes, consent/stale-review
  rejection, invalid sources/bases/notes, unsupported metadata and legacy reads.
- Remaining: streaming beyond RAM/chunk-level resume, broader language/quality/
  PII/contamination policies, permission-evidence workflows beyond user declarations
  and remaining acceptance verification. Physical/Windows blockers remain open
  and skipped. No external collection or rights inference occurred; generated
  ZIPs/fixtures, downloaded weights and unrelated user edits are excluded from Git.

P3-LMF-02 partial progress · resumable bounded-chunk original source storage · 2026-11-20:
- [ ] P3-LMF-02 remains open. Added explicit macOS source selection, local whole-file
  hashing with the installed shasum utility, confirmation, progress/pause and saved
  source resume controls. The client streams at most 65536 decoded bytes per
  request; it does not read the complete file into a Dart byte array. Resume
  requires the selected file's full hash and size to match the saved source.
- Version-1 source sessions store original bytes separately from prepared datasets.
  The backend validates exact offsets, chunk bounds and literal consent; identical
  committed retries are idempotent. Source writes are flushed before atomic offset
  updates. Recovery discards only an uncommitted tail after an interrupted offset
  write, preserving committed bytes. Final verification hashes the stored file
  incrementally and marks it stored_not_prepared only on exact size/hash match.
  Completed sources reject further chunk writes. No training/approval transfer or
  automatic preparation occurs. Protocol metadata supports sources up to 1 TiB;
  actual ingestion remains subject to available storage.
- Native verification: rebuilt/launched ALMG, selected a generated 67,108,864-byte
  local text fixture and confirmed upload. Paused at 28,180,480 committed bytes,
  restarted ALMG, reopened the identical pending record, reselected the original
  hash-matching file and explicitly resumed. Source 804c921e8c42470a8cf329915ce8a32c
  completed at the original size/hash. Actual backend instrumentation observed
  1,024 requests with maximum 87,384 base64 characters (65536 decoded bytes).
  Verified stored source hash equals the unchanged original, and no prepared
  dataset or trial was created. The fixture used a small per-chunk I/O delay to
  make native pausing observable. Evidence: /tmp/almg-stream-upload-qa/{paused-ui.json,
  restarted-paused-ui.json,stored-ui.json,chunk-metrics.json,large-source.txt}.
- Validation: 338 Python tests with ALMG_METAL_TESTS=1, 20 Flutter tests and clean
  Flutter analysis. New cases cover chunked resume, idempotent retries, committed
  offsets, interrupted offset-write recovery, consent/bounds, incomplete sealing,
  wrong final hashes, bounded Dart chunks and pause/resume without retransmission.
- Remaining: streamed UTF-8 validation/extraction, normalization and indexed
  preparation, chunk-level processing resume, prepared-stream dataset/training
  integration, verification with sources larger than host RAM, optional provider
  contracts and remaining acceptance coverage. This slice is original-source
  storage, not a prepared language-model dataset or completed streaming acceptance.
  Other existing language/quality/PII/permission limitations remain documented.
  Physical/Windows blockers stay open and skipped. No external collection occurred;
  generated large sources/uploads, weights and unrelated edits are excluded from Git.

P3-LMF-02 partial progress · transactional streamed text normalization/indexing · 2026-11-20:
- [ ] P3-LMF-02 remains open. Verified stored sources now offer explicit line-based
  index preparation and saved-index review. Each UTF-8 line is a document (64 KiB
  including line ending); preparation strips an initial BOM, normalizes NFC and
  whitespace, applies existing bounded word validation, counts empty lines and
  deduplicates normalized content by SHA-256. Hash buckets assign stable
  train/validation/test partitions. Method, runtime, source hash and first raw-line
  hashes/byte offsets are retained for provenance; duplicate occurrences are counted.
- SQLite stores text and processing state on disk with a 2 MiB page cache and
  file-backed temporary storage. Processing uses bounded line reads and steps
  limited by line/byte budgets. Each batch updates offsets/counts/documents in one
  transaction; connections close after each operation. Pause occurs between batches.
  Invalid UTF-8, unsupported lines or source/implementation changes stop safely
  without losing earlier checkpoints. Completed publication binds the immutable
  SQLite checksum and a version-1 manifest revision; interrupted publication can
  resume without reinserting rows or incrementing duplicate counts again.
- Native verification: rebuilt/launched ALMG, selected the verified 67,108,864-byte
  source and explicitly confirmed the line policy. Paused index
  7c72d600ff9e492f9371f977f2e18ab0 after 2,020,000 lines/56,560,212 committed bytes.
  Restarted both app and backend, reopened the identical checkpoint (no automatic
  work), and explicitly resumed. Completed at 2,396,737 lines, three unique records
  and 2,396,734 duplicates, matching an independent bounded line scan. Compared all
  normalized texts/occurrences and first-line raw hashes/offsets, verified source
  hash unchanged and the published SQLite/manifest integrity through the normal
  reader. No small prepared dataset or training trial was created. Evidence:
  /tmp/almg-stream-index-qa/{confirmation-ui.txt,paused-index-ui.json,
  restarted-index-ui.json,complete-index-ui.json,reference.json}, plus the index's
  records.sqlite3/manifest.json under jobs/decoder-stream-indexes/.
- Validation: 342 Python tests with ALMG_METAL_TESTS=1, 20 Flutter tests and clean
  Flutter analysis. New cases verify bounded step continuation, Unicode/BOM and
  whitespace normalization, deduplication/provenance, invalid-input rollback,
  oversized lines, consent, source/code changes, interrupted publication recovery,
  immutable complete reads and manifest tampering rejection.
- Remaining: training/tokenizer/evaluation/quality/PII/permission/export integration
  for large indexes, verification using sources larger than host RAM, optional
  external provider contracts and remaining acceptance coverage. The index is
  explicitly not trainable yet; 64 MiB verification does not establish beyond-RAM
  acceptance. Physical/Windows blockers remain open and skipped. No external
  collection occurred; generated sources/indexes, weights and unrelated edits are
  excluded from this commit.

P3-LMF-02 partial progress · bounded indexed-record review and local findings · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed indexes now offer read-only record
  review with next/previous/first-page navigation, saved-split filters and source
  details. Keyset cursors bind the immutable index revision and filter; requests
  return at most 20 records (native default 10). Client back history is bounded to
  50 pages, with a first-page reset for long review sessions.
- Each record shows a maximum 512-character excerpt, occurrence count, normalized
  character count, first source line/byte offset, raw-line/source/group hashes and
  current local hygiene/privacy findings. Detected contacts are masked before
  excerpt truncation; total match counts remain accurate while detailed findings
  are capped at 20 per record. The analysis version/hash and normalized-offset
  convention are disclosed. Other personal information may remain. Pages are
  advisory and do not filter stored data or change training/evaluation gates.
- Native verification: rebuilt/launched ALMG, opened completed index
  5c62810a0727435d916d443045786cc5 and reviewed ten then three records, covering all
  thirteen fixture records without overlap. Verified masked contact values,
  bounded/truncated excerpts and expanded provenance matching the page response.
  Back navigation restored the exact first page; validation filtering returned
  the correct two records. Rebuilt/restarted the final dialog and verified the
  first-page reset from page two returned the original response. SQLite/manifest
  bytes stayed identical and no trial was created. Also read the previously
  completed 64 MiB index through the new endpoint without rewriting it. Evidence:
  /tmp/almg-stream-review-qa/{first-page-ui.txt,second-page-ui.txt,provenance-ui.json,
  validation-ui.txt,restarted-first-page-ui.txt,pages.jsonl,before.json}.
- Validation: 346 Python tests with ALMG_METAL_TESTS=1, 23 Flutter tests and clean
  Flutter analysis. New cases cover complete non-overlapping pages, split/cursor
  binding, consent/limits, dense-contact masking and finding caps, unavailable or
  corrupt indexes, immutable artifacts, next/back/filter/reset navigation, bounded
  history and retry after a failed page. A viewport-dependent test was corrected
  to scroll the source disclosure into view before opening it.
- Remaining: full-index quality/PII/language/permission/contamination processing,
  tokenizer/training/evaluation/export integration for large indexes, beyond-host-
  RAM verification, optional external-provider contracts and remaining acceptance
  coverage. Read-only page findings do not establish full-index admission checks.
  Physical/Windows blockers remain open and skipped. No external collection
  occurred; generated sources/indexes/page traces, weights and unrelated edits
  are excluded from this commit.

P3-LMF-02 partial progress · resumable full-index hygiene/contact audits · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed indexes now offer an explicitly
  confirmed full-index diagnostic scan, pause/resume, saved reports and paged
  findings. The scan checks every unique normalized record with the current
  hygiene/contact heuristics, counts original occurrences separately and retains
  affected source/group/split, first line/byte offset and raw-line hashes. Original
  text/contact values are omitted from the diagnostic store; detailed contact
  findings remain bounded per record, with complete aggregate match counts.
- SQLite transactions checkpoint the group cursor, counters and findings together.
  Batches use record/character budgets and the existing bounded cache/file-backed
  temporary storage. The source index is opened read-only, bound by revision/file
  hash and checked for changes. Audit code plus Python/SQLite/Unicode runtime are
  bound for resume; changed implementations/runtimes require a newly reviewed
  audit while preserving old progress. Publication records an immutable database
  checksum/revision and recovers after an interrupted final manifest write without
  recounting records. This is diagnostic only and changes no training admission.
- Native verification: rebuilt/launched ALMG, confirmed a scan of 2,000 known local
  fixture records, paused audit bcfb9b22cb944cac8db69292ceec65f5 at 1,200 checked,
  restarted both app and backend and reopened the identical pending checkpoint
  without automatic work. Explicit resume completed all 2,000: 667 hygiene-review
  records, 667 privacy records/matches, 1,334 finding records and average score
  92.07, matching the fixture's independent expected totals. Verified absence of
  raw contact values in the audit database and unchanged source-index files.
  Opened native finding pages, matched provenance to the actual indexed/original
  source bytes, verified non-overlapping next pages and validation-split filtering.
  No trial was created. The fixture used a 0.6-second batch delay solely to make
  pausing observable. Evidence: /tmp/almg-full-audit-qa/{confirmation-ui.txt,
  paused-audit-ui.json,restarted-audit-ui.json,complete-audit-ui.json,
  finding-provenance-ui.json,findings-first-ui.txt,findings-second-ui.txt,
  validation-findings-ui.txt,finding-pages.jsonl,before.json}.
- Validation: 350 Python tests with ALMG_METAL_TESTS=1, 23 Flutter tests and clean
  Flutter analysis. New coverage verifies complete unique-record scan/resume,
  occurrence-weighted contact totals, immutable originals, raw-text omission,
  batch rollback/retry, interrupted publication, cursor/report integrity, consent,
  source changes and code/runtime invalidation. Existing shared viewer navigation
  and retry tests still pass.
- Remaining: full-index language/permission/contamination policies, tokenizer/
  training/evaluation/export integration, beyond-host-RAM verification, optional
  external provider contracts and remaining acceptance coverage. Current heuristic
  checks do not establish comprehensive PII detection or evaluation cleanliness.
  Physical/Windows blockers remain open and skipped. No external collection
  occurred; generated audits/indexes/trace fixtures, weights and unrelated edits
  are excluded from this commit.

P3-LMF-02 partial progress · private streamed-index export · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed indexes now offer a reviewed
  private local folder export of their immutable manifest and normalized-text
  SQLite database, with an export receipt preserving source identity and hashes.
  The review explicitly discloses personal text and excludes the original raw
  source, saved audits and training approvals. No external collection occurs.
- Files are copied in chunks of at most 65,536 bytes, checked against reviewed
  hashes locally, and fully verified by the backend before publication. Consent,
  stale reviews and changed files are checked; cancellation or failure removes
  only the operation's own staging folder. Existing files are preserved.
- Local app verification: rebuilt and launched the native macOS app, opened the
  completed 2,000-record fixture index, confirmed its export review and selected
  a local folder. Observed “Private text index saved”. The resulting three-file
  package contains 996,720 bytes of index data copied in 17 bounded requests.
  Both exported file hashes match the unchanged originals; restoring the index
  in an isolated directory verifies its revision, all 2,000 records and source
  provenance/first-line offsets. Evidence: /tmp/almg-stream-export-qa/
  {review-ui.json,saved-ui.txt,chunk-metrics.json,verification.json}.
- Validation: 353 Python tests, 25 Flutter tests and Flutter analysis pass.
  Tests cover exact reconstruction, provenance, consent/stale/change rejection,
  bounded client transfers and cleanup after cancellation/hash mismatch.
- Remaining: streamed-index tokenizer/training integration and contamination
  admission, larger-than-RAM acceptance, broader extraction/provider contracts
  and remaining dataset-engineering criteria. Import was verified through the
  existing index reader; no native streamed-index import workflow is delivered.
  Physical power and Windows blockers remain separate and skipped. Generated
  packages, fixtures, weights and unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · optional data-provider boundary · 2026-11-20:
- [ ] P3-LMF-02 remains open. Added a versioned optional provider contract with
  review/collect/resume operations, immutable source identity/hash/byte metadata,
  source permission declarations, 64 KiB transfer bounds and checkpoint binding
  requirements. Its local metadata validator rejects missing/extra fields,
  credential fields, invalid hashes, unsupported permission bases and bad lengths.
  A valid source review preserves provenance and explicitly grants no collection
  consent, verified source permission or training approval.
- Native “Optional dataset providers” reports no connected adapters and exposes
  the versioned requirements on demand. ADAP is an example only, not an installed
  integration or dependency. Existing app consent/source restrictions must apply
  to any future adapter; this change performs no external collection or ingestion.
- Local app verification: rebuilt/launched ALMG against an isolated local fixture,
  opened Training recipe details → Optional dataset providers, observed the
  disconnected-provider message and expanded the contract. Captured native JSON
  exactly matches the backend definition and revision
  82ef8ec561f11f132389940a04e4181f417df87a8c45c1ed62da21928f1b5e39.
  A synthetic local source review preserves every source field without authorizing
  collection. Evidence: /tmp/almg-provider-qa/{availability-ui.txt,contract-ui.txt,
  contract-ui.json,source-review-fixture.json}.
- Validation: 356 Python tests, 25 Flutter tests and Flutter analysis pass. Contract
  tests verify stable version/revision, independent returned values, provenance
  binding, no authorization side effects and invalid/credential metadata rejection.
- Remaining: actual optional adapter implementations and consent-bound collection/
  resume enforcement require separate integration work; contract definitions do
  not establish those capabilities. Streamed tokenizer/training/contamination
  integration, larger-than-RAM acceptance and other dataset-engineering criteria
  remain open. Physical power and Windows blockers remain separate and skipped.
  No generated fixtures, artifacts, weights or unrelated edits are committed.

P3-LMF-02 partial progress · reviewed Markdown source ingestion · 2026-11-20:
- [ ] P3-LMF-02 remains open. Local document selection now accepts .md and
  .markdown alongside .txt for preparation, saved inputs and incremental additions.
  These are original UTF-8 text sources: Markdown markup remains literal; no
  rendered extraction or remote resource fetching is performed. Original bytes
  and filenames continue through the existing provenance/hash pipeline.
- Shared reads enforce 64 KiB per document and 128000 bytes per selection while
  reading, use a bounded range, reject size changes and decode UTF-8 strictly.
  This replaces an unbounded read after a size check. New immediate preparations
  show filenames, actual byte counts, tokenizer and literal-Markdown behavior,
  then require “Confirm dataset preparation” before publishing a local dataset.
- Local app verification: rebuilt/launched ALMG with an isolated fixture, selected
  ocean.txt (75 bytes), sky.markdown (81 bytes) and orchard.md (89 bytes) using the
  native chooser. The review displayed all three sizes and no dataset existed
  before confirmation. After confirmation, native dataset
  4c2d83ce32be4b119dbbb2a57a059c75 reopened through the integrity-checking reader;
  all three original SHA-256 hashes matched, accented text/CRLF source provenance
  survived and splits contained one document each. Markdown text remained literal;
  no training started. Evidence: /tmp/almg-markdown-qa/{review-ui.txt,
  prepared-ui.txt,prepared-ui.json,verification.json}.
- Validation: 356 Python tests, 27 Flutter tests and Flutter analysis pass. Added
  reader tests cover exact original byte preservation, strict invalid UTF-8
  rejection, actual oversized data despite a stale size, a size change during
  reading, aggregate limits and excessive file counts.
- Remaining: rendered/richer document extraction, streamed tokenizer/training and
  contamination integration, larger-than-RAM acceptance and other dataset criteria.
  The small-dataset limits remain explicit; this is not a large-document importer.
  Physical power/Windows blockers remain open and skipped. Generated fixtures,
  datasets, weights and unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · resumable streamed byte-token statistics · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed indexes now offer an explicitly
  confirmed fixed UTF-8 byte-alphabet scan. Versioned reports contain all 256 token
  counts by split, unique-record versus original-occurrence weighted totals,
  character/token totals, record-length extrema and counts over the current
  byte tokenizer's 4096-byte document limit. Special tokens are excluded. This
  performs no tokenizer fitting, word/BPE analysis or training admission.
- Scan progress uses bounded batches (100 records/about 1 MiB of text), keyset
  cursors and atomic report replacement. Report revisions bind index/source
  provenance, implementation/runtime and the counting method. Source signatures
  are checked per batch and full index integrity at start/completion. Changed
  inputs/code reject resume while preserving progress. Completed reports remain
  unchanged; raw record text is not stored in the report.
- Local app verification: rebuilt/launched ALMG, confirmed the scan over the
  isolated 2,000-record index and paused after 200 records. Restarted both backend
  and app, reopened the saved report and verified identical content/revision,
  then resumed to completion. Native report fe1b40880565458891c47e00c83ccb04
  contains 473,857 byte tokens. Every one of the 256 histogram counts per split,
  including occurrence weights, matches an independent source-index recount.
  Source manifest/database bytes remain unchanged; no trial/tokenizer was created.
  Evidence: /tmp/almg-byte-stats-qa/{consent-ui.txt,paused-ui.json,
  restarted-paused-ui.json,completed-ui.json,completed-ui.txt,verification.json}.
- Validation: 359 Python tests, 27 Flutter tests and Flutter analysis pass. New
  tests cover exact counts, duplicate weighting, Unicode byte equivalence, long
  record warnings, process reload, failed publication recovery, unchanged source,
  consent/code/source rejection and report integrity checks.
- Remaining: saved/train-fitted tokenizer and streamed training integration,
  contamination/near-duplicate policies, broader extraction and larger-than-RAM
  acceptance, plus other dataset-engineering criteria. This diagnostic does not
  enable training for long records or establish evaluation cleanliness. Physical
  power/Windows blockers remain separate and skipped. Generated reports, fixture
  data, artifacts, weights and unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · streamed source permission history · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed indexes now offer source-bound
  permission review and confirmed user declarations (created source, recorded
  permission or needs review), with a required evidence/source note. Append-only
  versioned records bind source hash, index revision, sequence and prior revision.
  History is bounded to 32 entries; old declarations and the source/index bytes
  remain unchanged. Declarations explicitly grant neither verified permission
  nor training approval. Stale reviews, repeated declarations and tampered history
  fail closed; existing progress/data are preserved.
- New version-2 private index export receipts include the complete reviewed source
  permission history and notes. Adding a declaration invalidates an outstanding
  export review. Existing saved packages are not rewritten; file payloads remain
  the same manifest and SQLite index. Export review explicitly discloses inclusion
  of permission notes. No external collection or rights verification is performed.
- Local app verification: rebuilt/launched ALMG, opened source permission history
  for the 2,000-record fixture index, selected a basis, entered a synthetic evidence
  note and confirmed. Native declaration revision
  02a6f32952226b3508670e826c1522f5ebe5b5e2a5b91948b5aa8799dc585f1c
  was reread unchanged in a separate process. Reviewed and completed native private
  export; export-manifest.json exactly matches the reviewed version-2 receipt and
  includes the saved declaration. Both exported index files match unchanged source
  files byte-for-byte. No training started. Evidence:
  /tmp/almg-stream-permission-qa/{empty-review-ui.json,confirmation-ui.txt,
  saved-review-ui.json,export-review-ui.json,export-saved-ui.txt,verification.json}.
- Validation: 362 Python tests, 27 Flutter tests and Flutter analysis pass. Tests
  cover immutable declaration chaining, exact exported history, source preservation,
  no approval transfer, stale export rejection, consent/validation/duplicate failures,
  incomplete indexes and tamper rejection.
- Remaining: actual permission verification/source-specific collection policies,
  streamed training/tokenizer and contamination integration, richer extraction,
  larger-than-RAM acceptance and other dataset criteria. Physical power/Windows
  blockers remain separate and skipped. Generated declarations, export packages,
  fixtures, weights and unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · resumable streamed language identification · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed indexes now offer confirmed,
  resumable dominant-language identification through the existing optional local
  macOS NaturalLanguage adapter. Processing is bounded to 100 records/about one
  million characters per batch. Unsupported/unavailable recognition remains
  explicit unknown; short text, confidence and margin rules match the existing
  small-dataset language report. No new provider dependency or network is added.
- Versioned SQLite reports preserve per-record source hashes, line/byte offsets,
  occurrences, split, candidates/confidence and unknown reasons while omitting
  source text. Summaries count languages by split. The native saved-report view
  supports pause/resume and bounded record details/pagination. No filtering or
  training approval changes. Source/code/runtime bindings and atomic transactions
  preserve committed progress on failure and reject changed inputs/implementations.
- Local app verification: rebuilt/launched ALMG with an isolated 601-record local
  multilingual index. Confirmed a real local scan, paused at 100 records, restarted
  backend and app, reopened identical saved progress, then resumed to completion.
  Report ac4736f8dae24fddb1f11ea1f266e667 contains 200 English, 200 French,
  200 Spanish and one explicit unknown (insufficient alphabetic text). Per-record
  rows independently match these totals and retain original source references.
  Exercised native record details and Next records (10 records per page). Original
  source-index hashes are unchanged and no training started. Evidence:
  /tmp/almg-stream-language-qa/{consent-ui.txt,paused-ui.json,restarted-ui.json,
  completed-ui.json,records-page-ui.txt,record-details-ui.json,next-page-ui.txt,
  verification.json}.
- Validation: 365 Python tests, 28 Flutter tests and Flutter analysis pass. Added
  coverage for full-population counts, reload/resume, transaction failure recovery,
  provider unavailable/short-text unknowns, source provenance/text omission, bounded
  revision-bound pagination, changed source/code/consent rejection and language-row
  rendering without invented hygiene/privacy findings.
- Remaining: probabilistic language identification does not establish language
  correctness for all text. Broader extraction, streamed tokenizer/training and
  contamination/near-duplicate integration, larger-than-RAM acceptance and other
  dataset criteria remain open. Physical power/Windows blockers stay separate and
  skipped. Generated reports, fixtures, artifacts, weights and unrelated edits are
  excluded from this commit.

P3-LMF-02 partial progress · resumable streamed near-duplicate diagnostics · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed indexes now offer an explicitly
  confirmed exhaustive unordered record-pair scan using the existing five-word
  shingle Jaccard rule (minimum 12 words, similarity >= 0.8). Near duplicates and
  cross-split potential evaluation contamination are reported with both source
  hashes, first-line/byte offsets, raw-line hashes, occurrences and split labels.
  Raw text is omitted. Exact duplicates were already grouped during indexing.
- Processing uses bounded record buffers and batches of at most 100 pairs/about
  one million compared characters, with a transactional pair cursor. Reports bind
  source index/revision, implementation/runtime and final database checksum. Native
  controls support pause/resume, saved reports and affected-pair inspection. Split
  filters match either pair endpoint. Changed inputs/code and failed batches retain
  committed progress. This diagnostic neither filters data nor grants training.
- The native review explicitly discloses exhaustive quadratic comparison cost.
  Memory is bounded, but runtime and worst-case findings storage can be quadratic;
  this is not an approximate scalable search or comprehensive semantic overlap test.
- Local app verification: rebuilt/launched ALMG with a 44-unique-record local
  fixture (45 original lines), confirmed the scan and paused at 200 of 946 pairs.
  Restarted backend/app, reopened identical saved state and resumed to completion.
  Report 4ab3994790b54eb5b956818c37d30d14 identifies exactly three near-duplicate
  pairs, all cross-split, matching an independent exhaustive recount. It reports
  43 short pairs skipped. Native findings expose both source locations/similarity;
  original index hashes are unchanged and no training started. Evidence:
  /tmp/almg-overlap-qa/{consent-ui.txt,paused-ui.json,restarted-ui.json,
  completed-ui.json,findings-ui.txt,pair-details-ui.json,verification.json}.
- Validation: 368 Python tests, 29 Flutter tests and Flutter analysis pass. Added
  tests cover all-pairs totals, exact expected cross-split findings, reload/resume,
  batch rollback, unchanged source, omitted text, pair pagination, either-endpoint
  split filtering, revision-bound cursors, changed source/code/consent rejection
  and overlap-row rendering.
- Remaining: streamed pre-training contamination admission, scalable candidate
  indexing/semantic policies, tokenizer/training integration, richer extraction,
  larger-than-RAM acceptance and other dataset criteria. Physical power/Windows
  blockers remain open and skipped. Generated reports, fixtures, artifacts, weights
  and unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · resumable contact-filtered streamed versions · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed original streamed indexes now offer
  confirmed contact-pattern filtering into a separate immutable index. Detected
  spans are replaced with [CONTACT_REDACTED]; Unicode/whitespace normalization,
  global exact deduplication and fresh hash-based splits apply to the derived
  text. Original source/index bytes stay unchanged. Existing bounded token/word
  constraints still apply; this is heuristic filtering, not comprehensive PII removal.
- Processing uses transactional batches of at most 100 parent records/about one
  million characters, with restart-safe progress. The derived SQLite lineage table
  binds every parent group to its derived group, original split, source line/byte
  location, raw-line hash, occurrences and replacement count. Parent permission
  declarations are retained as a snapshot in the derivation; notes are not filtered.
  No audits, training approvals or evaluation-cleanliness claims transfer. Repeated
  filtering of an already filtered version is rejected. Changed source/code and
  failed batches preserve committed progress.
- Reuses the existing immutable index envelope with additive derivation/lineage
  metadata, leaving legacy indexes untouched. Existing readers, record review,
  audit and private export remain usable; the backend routes derived preparations
  to their own worker. No existing unfinished index implementation hash changes.
- Local app verification: rebuilt/launched ALMG with an isolated 2,000-record
  original index. Confirmed filtering, paused after 200 records, restarted backend
  and app, reopened identical state and resumed the same child
  b8eeccc3a0ec4825aafb253f6e6c10cd to completion. It replaced 667 spans in 667
  records, retained all 2,000 records and lineage entries, and has zero remaining
  matches under the current contact patterns. All lineage source fields match the
  original records. Native record review and private export succeeded; restoring
  the exported manifest/SQLite in isolation preserved its complete lineage and
  integrity. Parent hashes are unchanged; no training started. Evidence:
  /tmp/almg-stream-contact-filter-qa/{consent-ui.txt,paused-ui.json,restarted-ui.json,
  completed-ui.json,record-review-ui.txt,export-review-ui.json,export-saved-ui.txt,
  verification.json}.
- Validation: 371 Python tests, 29 Flutter tests and Flutter analysis pass. New
  tests cover reload/resume, collision deduplication and occurrence conservation,
  source/permission lineage, export integrity, rollback after partial batch writes,
  source/code changes, consent/stale reviews, and original preservation.
- Remaining: broader PII policies, streamed pre-training contamination admission,
  tokenizer/training integration, richer extraction, larger-than-RAM acceptance
  and other dataset criteria. Physical power/Windows blockers remain open and
  skipped. Generated filtered datasets, fixtures, export packages, weights and
  unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · reviewed offline HTML text extraction · 2026-11-20:
- [ ] P3-LMF-02 remains open. Added a separate native local HTML preparation
  workflow for 3–16 UTF-8 .html/.htm files under the existing 64 KiB/file and
  128000-byte selection limits. A versioned static parser extracts body text,
  decodes entities and omits head/script/style/template/noscript/comment content
  plus hidden/aria-hidden=true sections. Nesting is bounded to 128 elements.
  No JavaScript runs or linked resources are fetched; CSS/layout/browser rendering
  are explicitly unsupported. Existing plain-text/Markdown semantics stay unchanged.
- Native review shows extracted previews, original/extracted byte lengths and
  progressively disclosed source hashes/method before confirmation. Prepared
  datasets use the existing UTF-8 byte tokenizer and preserve original HTML hashes
  linked to extracted-text hashes in versioned derivation provenance. Raw HTML is
  not included in the dataset/export. This does not grant permission or start
  training. Changed source bytes or extraction reviews reject publication.
- Local app verification: rebuilt/launched ALMG with three isolated HTML sources,
  selected them through the native chooser and inspected previews. Expected body
  text, Unicode and decoded entities remain; hidden/executable fixture content is
  absent. No dataset existed before confirmation. Confirmed dataset
  a98aeef12cb04f44ba7d768a3d9be39b, verified original/extracted hashes and normalized
  text, then completed native private ZIP export. Exported manifest/provenance
  exactly matches the saved dataset; no raw HTML entries are present. Restarted
  app/backend and reopened identical saved metadata without re-extracting inputs.
  No training started. Evidence: /tmp/almg-local-html-extraction-qa/{preview-ui.txt,
  review-ui.json,dataset-ui.json,export-review-ui.json,export-saved-ui.txt,
  restarted-dataset-ui.json,verification.json}.
- Validation: 374 Python tests, 29 Flutter tests and Flutter analysis pass. Added
  coverage for excluded content/entity decoding, original-byte/extracted hashes,
  independently revised provenance, unchanged saved readers/export, consent/stale
  review rejection, invalid UTF-8, empty extraction, oversized/deep inputs and
  unsupported file types. Existing fixtures remain readable; no existing dataset
  implementation hashes or stored files are rewritten by the new extraction module.
- Remaining: richer formats/rendered extraction and broader document policies,
  streamed training/tokenizer/contamination integration, larger-than-RAM acceptance
  and other dataset criteria. HTML is a bounded synchronous preparation, with
  publication through the existing atomic dataset path; no resumable HTML draft
  workflow is delivered. Physical power/Windows blockers remain open and skipped.
  Generated inputs, datasets, exports, weights and unrelated edits are excluded.

P3-LMF-02 partial progress · durable reviewed HTML preparations · 2026-11-20:
- [ ] P3-LMF-02 remains open. The HTML extraction review now offers explicit
  “Save HTML preparation draft”, preserving the original bounded inputs and exact
  extraction review locally without publishing a dataset. Native saved-draft views
  expose the stored review, implementation status and explicit prepare/open actions.
  No automatic recovery, collection or training starts. Original HTML is retained
  in the private draft only; prepared dataset/export contents keep their prior scope.
- New versioned HTML-draft records bind original inputs, extraction review and
  implementation hashes. Atomic publication uses the draft's stable dataset ID.
  If the dataset is published but the final draft record write fails, retry verifies
  and adopts the existing matching dataset instead of creating another. Completed
  drafts reopen the same integrity-checked dataset. Changed code, stale reviews or
  tampered inputs reject processing and preserve existing data. Plain-text drafts
  and previously published datasets are not rewritten.
- Local app verification: rebuilt/launched ALMG, selected three HTML fixtures and
  saved draft b5f55e2ed2db4008a376c88a782bc9d2 from its native extraction review.
  No dataset existed. Restarted backend/app, reopened identical draft/review and
  confirmed that no automatic preparation occurred. “Prepare saved HTML inputs”
  then published dataset b5f55e2ed2db4008a376c88a782bc9d2 without selecting files
  again. Saved original bytes remain unchanged. Reopened the completed draft and
  its dataset through native controls; metadata matches exactly and publication
  count remains one. A separate fresh-process check confirms the prior HTML
  dataset remains readable unchanged. Evidence: /tmp/almg-html-draft-recovery-qa/
  {review-ui.txt,saved-draft-ui.json,restarted-draft-ui.json,prepared-ui.json,
  completed-draft-ui.json,reopened-dataset-ui.json,verification.json}.
- Validation: 377 Python tests, 29 Flutter tests and Flutter analysis pass. New
  tests cover original-input preservation, reload, explicit consent, stable identity,
  idempotent reopen/retry, recovery after publication plus record-write failure,
  stale review/code rejection, tampered-input rejection and no training side effects.
- Remaining: streamed training/tokenizer/contamination admission, richer document
  policies, larger-than-RAM acceptance and other dataset criteria. HTML drafts
  retain the existing small-input bounds; they are not a large-HTML streaming
  implementation. Physical power/Windows blockers remain open and skipped.
  Generated drafts, datasets, fixtures, artifacts, weights and unrelated edits are
  excluded from this commit.

P3-LMF-02 partial progress · saved streamed fixed-byte tokenizer artifacts · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed byte-distribution reports now
  offer confirmed publication of the existing fixed 256-byte tokenizer format.
  The artifact binds only unique training-split text in stable group order, using
  the same canonical NFC text-array hash as the existing small byte tokenizer.
  Validation/test text is excluded from that binding. No vocabulary is learned,
  special tokens added or training approval granted.
- Preparation verifies the exact reviewed report and immutable index, validates
  every record against the current 4096-byte document limit with bounded reads,
  checks split populations and rechecks source integrity before atomic publication.
  Versioned manifests bind source provenance, index/report revisions, tokenizer
  fingerprint and file checksum. Saved per-index inventory verifies and reloads
  the standard byte-tokenizer artifact. Long records, stale/incomplete reports,
  missing training records and altered artifacts fail closed.
- Local app verification: rebuilt/launched ALMG, opened the completed 2,000-record
  byte report, reviewed/confirmed tokenizer publication, then inspected saved
  artifact 21ec94db1631466da69b4cad007a652d. Its training-only hash independently
  matches all 1,599 unique training records in canonical order (beyond the small
  list-fit helper's document cap). The standard tokenizer reloads and round-trips
  UTF-8 text. Restarted backend/app and reopened identical metadata through native
  saved-tokenizer inventory. Source index files are unchanged; no training started.
  Evidence: /tmp/almg-stream-byte-tokenizer-qa/{consent-ui.txt,saved-ui.json,
  restarted-ui.json,verification.json}.
- Validation: 380 Python tests, 29 Flutter tests and Flutter analysis pass. Added
  tests compare the artifact with the existing training-only byte fit, independently
  reject an all-split hash, check Unicode round-trip/source preservation, consent/
  stale/incomplete report rejection, oversized records and artifact tampering.
- Remaining: streamed token windows/training and contamination admission, broader
  tokenizer algorithms/policies, larger-than-RAM acceptance and other dataset
  criteria. Final artifact validation/hashing is one bounded-memory scan with
  atomic publication; it does not yet persist an intermediate hash state for
  resuming that final pass. The existing byte document limit remains explicit.
  Physical power/Windows blockers stay open and skipped. Generated artifacts,
  reports, fixture data, weights and unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · overlap-bound streamed token windows · 2026-11-20:
- [ ] P3-LMF-02 remains open. Saved streamed byte tokenizers now offer confirmed
  next-token window preparation, requiring a completed overlap report for the exact
  same immutable index/revision. Cross-split near-duplicate findings block this
  preparation before any window files are created. The accepted lexical method
  and exhaustive pair coverage are checked; skipped short pairs and semantic
  contamination limits remain explicit. This is not model training admission.
- Versioned SQLite artifacts store windows of at most 17 byte IDs with stride 16,
  preserving document boundaries and original splits. Per-record lineage retains
  source group, line/byte position, raw-line hash, occurrence count and token count.
  Exact duplicates are not re-expanded. Token IDs encode source text and may contain
  personal information, as disclosed before confirmation. No training/approval starts.
- Batches are bounded to 100 records/about one million characters, with atomic
  record/window/cursor updates. Index, tokenizer and overlap revisions, signatures,
  runtime and implementation are bound and revalidated before final publication.
  Saved views support pause/resume and bounded token/source detail pagination.
- Local app verification: rebuilt/launched ALMG with clean and contaminated local
  fixtures. Native preparation with three cross-split findings was rejected before
  creating files. The clean preparation paused at 200 of 401 records; after backend/
  app restart, identical state reopened and resumed to completion. Artifact
  0fddce1a8a71436e802059c168fa8099 contains 6,344 train, 764 validation and 702 test
  windows (7,810 total), with 121,308 target tokens. Every window independently
  matches its source slice; all document/split boundaries and lineage match source
  data. Native window detail and Next records review work. Source bindings remain
  unchanged and no training started. Evidence:
  /tmp/almg-stream-window-preparation-qa/{blocked-ui.txt,consent-ui.txt,paused-ui.json,
  restarted-ui.json,completed-ui.json,windows-page-ui.txt,window-details-ui.json,
  next-page-ui.txt,verification.json}.
- Validation: 383 Python tests, 30 Flutter tests and Flutter analysis pass. New
  tests verify exact windows/targets, split/source preservation, reload/resume,
  nonoverlapping revision-bound pages, cross-split/consent/stale review rejection,
  rollback after partial writes, code/source change rejection and token-row rendering.
- Remaining: actual streamed model training/scheduling and its final admission,
  broader contamination/PII policies, scalable overlap search, richer tokenizers,
  larger-than-RAM acceptance and other dataset criteria. The lexical gate alone
  does not establish evaluation cleanliness. Physical power/Windows blockers remain
  open and skipped. Generated windows, reports, fixtures, artifacts, weights and
  unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · bounded source-bound model-input batches · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed token windows now have a read-only
  model-input adapter returning bounded rectangular inputs, shifted next-token
  targets, sequence lengths and required loss masks, with source provenance per row.
  Width is 16 and batch size is limited to 1–16 windows. Numeric zero padding is
  masked storage, not a new vocabulary token. Splits and document boundaries stay
  separate; duplicate occurrences are not expanded and no model is executed.
- Each read requires the exact window review and revalidates the current index,
  tokenizer and completed overlap evidence against stored revisions. Stale sources,
  reviews/cursors, cross-split requests, invalid sizes and token contracts reject
  without changing artifacts. The new response format is versioned; existing
  stored artifact schemas and pending preparation implementation hashes are unchanged.
- Native “Inspect model input batches” supports train/validation/test selection,
  bounded Next/First controls, recoverable errors and progressively disclosed
  arrays/masks/source references. Token IDs may encode personal text, as disclosed;
  this does not grant training approval or start a model.
- Local app verification: rebuilt/launched ALMG against an isolated copy of the
  completed 401-record window fixture. Inspected real training arrays, paged to
  a partial final window (sequence lengths [16,16,16,4]) and verified padded values
  are zero with zero loss mask. Selected validation, paged and reset to the first
  batch; reset output matches exactly and all rows remain validation-only. Every
  captured input/target slice, mask and source reference independently matches
  source data. All five source artifact namespaces remain byte-for-byte unchanged;
  no training started. Evidence: /tmp/almg-stream-model-batch-qa/{first-batch-ui.json,
  padded-batch-ui.json,padded-view-ui.txt,validation-batch-ui.json,
  reset-validation-batch-ui.json,verification.json}.
- Validation: 386 Python tests, 32 Flutter tests and Flutter analysis pass. New
  tests cover complete training-population coverage, correct shifts/padding/masks,
  held-out isolation, cursor/page limits, stale review/source rejection, source
  preservation and native-widget paging/reset/split/retry behavior.
- Remaining: actual streamed optimization, scheduling, checkpoint cursor binding
  and final training admission; shuffling/sampling weights and broader/scalable
  contamination policies; larger-than-RAM acceptance and other dataset criteria.
  Revalidation currently rehashes source artifacts for correctness; caching and
  large-corpus throughput remain future work. Physical power/Windows blockers
  stay open and skipped. Generated batches, fixtures, artifacts, weights and
  unrelated edits are excluded from this commit.

P3-LMF-02 partial progress · confirmed masked Metal optimizer diagnostic · 2026-11-20:
- [ ] P3-LMF-02 remains open. The model-input inspector now offers a separately
  confirmed five-step diagnostic using the existing registered from-scratch decoder
  initializer (fixed byte vocabulary, seed 7, SGD learning rate 0.05). It optimizes
  only the exact inspected training batch, verifies padding-target loss/gradient
  invariance and CPU/Metal inference parity, and checks that all parameter tensors
  changed with finite values and reduced batch loss. Source bindings are rechecked
  after GPU execution. Model weights are discarded; no candidate/bundle is saved.
- The first four validation/test windows are explicitly partial forward-only probes,
  not complete evaluation or a release gate. Versioned numerical reports preserve
  source-batch/provenance/implementation bindings and can be reopened through native
  saved-check inventory. No training/release approval is granted. Cancellation,
  stale data and failed checks publish no model/report. Inspector actions now wrap
  on smaller windows and the error panel scrolls, preserving retry access.
- Local app verification: rebuilt/launched ALMG on a real inspected partial batch
  with sequence lengths [16,16,16,4]. Cancelled the confirmation and verified no
  output, then explicitly confirmed the Metal run. Report
  7146586c8cfd493fbb77246712461245 records loss 5.53477955 → 5.33783436, all nine
  parameter tensors changed, 12 padded positions, zero masked-target loss error,
  gradient error 1.49011612e-8 and CPU inference error 3.67044014e-8. Restarted
  backend/app and reopened identical saved evidence without rerunning optimization.
  All five source artifact namespaces remain byte-for-byte unchanged; only one
  diagnostic JSON exists and no decoder model/trial files were saved. Evidence:
  /tmp/almg-masked-optimizer-native-qa/{training-batch-ui.json,consent-ui.txt,
  report-ui.json,verified-ui.txt,restarted-report-ui.json,verification.json}.
- Validation: 389 Python tests (including actual Metal updates), 33 Flutter tests
  and Flutter analysis pass. New coverage checks separate consent/cancellation,
  stale-batch rejection before initialization, real masked SGD/tensor updates,
  padding invariance, CPU parity, report integrity, post-GPU source-change rejection,
  no model saving and validation-split optimizer exclusion. The small-window retry
  regression found during verification is fixed and passes.
- Remaining: full streamed optimization, Qwen-supervised trial planning, scheduling,
  checkpoint/cursor recovery and complete held-out evaluation/admission; broader
  dataset policies, scalable overlap processing and larger-than-RAM acceptance.
  This five-step numerical check does not deliver a usable trained model or establish
  corpus quality. Physical power/Windows blockers stay open and skipped. Generated
  reports, fixtures, artifacts, weights and unrelated edits are excluded from Git.

P3-LMF-02 partial progress · bounded committed upload batches · 2026-11-20:
- [ ] P3-LMF-02 remains open. New streamed source sessions advertise up to sixteen
  64 KiB chunks per request (1 MiB decoded maximum). One source flush and atomic
  offset-record update commits each batch, reducing request/metadata-commit count.
  Every chunk is validated before any batch write. Exact retries verify committed
  bytes; interrupted record writes discard only the uncommitted tail on recovery.
- Source schema version 1 gains an optional batch-capability field. Legacy records
  without it keep the single-chunk path and are not automatically upgraded. Existing
  single-chunk endpoints remain bounded and supported. Flutter buffers only the
  advertised bounded batch, acknowledges offsets exactly and pauses at committed
  boundaries. Only the UUID-specific batch endpoint receives the larger bounded
  request limit; other request limits stay unchanged.
- Local app verification: rebuilt/launched ALMG, selected/confirmed a 64 MiB local
  fixture and paused at 6 MiB. Restarted backend/app, reopened identical source
  070b200396a042a2b252cacfa26a9958, reselected the original file for hash matching,
  then resumed the same session to stored_not_prepared. Final original/stored
  SHA-256 hashes match. Measured 64 upload requests versus 1,024 legacy-sized
  requests for the same bytes, with at most sixteen chunks/1 MiB per batch. This is
  a request-count comparison, not a wall-time benchmark. No training started.
  Evidence: /tmp/almg-bounded-upload-batch-qa/{consent-ui.txt,paused-ui.json,
  restarted-ui.json,completed-ui.json,first-run-metrics.json,metrics.json,
  verification.json}.
- Validation: 391 Python tests, 34 Flutter tests and Flutter analysis pass. Added
  tests verify one metadata commit per batch, retry equality, failed-commit tail
  recovery, invalid/oversized batch rejection before writes, legacy-record fallback
  and bounded client batch pause/resume with exact reconstructed bytes.
- Larger-than-RAM acceptance remains open with a concrete scratch-space constraint:
  this host has 36 GiB physical RAM and about 60 GiB free on the fixture volume.
  A straightforward source-plus-backend-copy fixture above RAM needs more than
  72 GiB, exceeding current safe free space. No oversized corpus was created and
  no user artifacts/weights were removed. Remaining verification requires adequate
  safe scratch space or a separately verified storage-efficient fixture strategy,
  then full native ingestion/preparation/hash and memory evidence. Skip this
  unchanged criterion while continuing independently actionable work.
- Other remaining scope includes full streamed optimization/planning/checkpoint
  recovery and broader/scalable dataset policies. Physical power/Windows blockers
  stay open and skipped. Generated sources, fixtures, metrics, weights and unrelated
  edits are excluded from this commit.

P3-LMF-02 partial progress · complete streamed held-out diagnostic evaluation · 2026-11-20:
- [ ] P3-LMF-02 remains open. The separately confirmed five-step masked optimizer
  diagnostic now evaluates every saved validation and test window in batches of
  at most sixteen. It sums masked token losses and correct predictions before
  dividing by real target counts, so short final windows and batches are weighted
  correctly. Held-out splits receive zero optimizer updates; source/overlap
  bindings are rechecked by the existing batch reader and again before publication.
- Incomplete population coverage, empty batches, invalid metrics and source changes
  fail without publishing a report. Consent describes complete evaluation and the
  need to rerun interrupted checks. Existing reports remain readable and explicitly
  identify legacy four-window probes. Only diagnostic JSON is saved; no model,
  training approval, usable-model claim or release is produced.
- Local app verification: rebuilt and launched native macOS ALMG on fixture port
  28830. Cancel saved nothing; explicit confirmation created report
  57ab492f592c40d49ced8323471b7a36. It evaluated all 764 validation windows /
  11,852 targets in 48 batches and all 702 test windows / 10,908 targets in 44
  batches. Correct predictions were 2,457 and 2,228; mean losses were
  5.464885849426455 and 5.461153159790263. An independent unpadded CPU pass over
  SQLite windows matched every population/correct count and loss within 1.8e-7.
  Native app restart reopened the identical report without another optimizer run.
  All 18 source/index/tokenizer/overlap/window fixture files stayed byte-identical;
  no decoder model was saved. Evidence: /tmp/almg-complete-heldout-native-qa/
  (consent-ui.txt, report-ui.json, reopened-report-ui.json, verification.json,
  build.log, restart.log and test logs); generated evidence is not committed.
- Verification: 393 Python tests passed with ALMG_METAL_TESTS=1, including real
  Metal optimization and rejection paths; 34 Flutter tests passed; Flutter analysis
  and diff checks passed. Multi-page regression verifies token weighting with a
  short final batch. Updated source/tests and this entry share one local commit.
- Remaining: full streamed training with Qwen-supervised planning, scheduling and
  checkpoint cursor binding, broader streamed dataset mixing/incremental ingestion,
  and the previously recorded larger-than-RAM acceptance/scratch-space blocker.
  This bounded-memory diagnostic evaluation is synchronous and not resumable;
  it does not satisfy the full training or larger-than-RAM acceptance criteria.
  Existing physical power/Windows and scratch-space blockers remain open and were
  skipped without repeating unchanged checks. No external collection or push.

P3-LMF-02 partial progress · reviewed local JSONL text ingestion · 2026-11-20:
- [ ] P3-LMF-02 remains open. Native dataset preparation now accepts 1 to 16 local
  UTF-8 .jsonl files containing 3 to 16 total text records, bounded to 64 KiB per
  source and 128000 bytes per selection. Every nonblank LF-delimited record must
  contain exactly one string field named text. Unknown/duplicate fields, malformed
  JSON, invalid Unicode, empty text, excessive nesting and count/byte overflows
  reject before publication; metadata is never silently discarded. Unicode line
  separators inside strings remain content; blank lines are counted and skipped.
- The explicit review shows each original line and bounded text preview. Confirmed
  preparation creates a new immutable dataset using the existing normalization,
  deduplication, split and UTF-8 byte tokenizer policies. Preview-free provenance
  retains original file hashes/bytes, original line numbers/raw-line hashes and
  extracted text hashes/bytes, and survives private export. Raw JSONL is excluded
  from that export. Source permission remains a user review; no collection,
  training approval, pretrained weights or training execution is introduced.
- Local app verification: rebuilt and launched native macOS ALMG with isolated
  fixture backend port 28831. Unsupported metadata was rejected with filename and
  line 1; reviewing then cancelling a valid Unicode/BOM/blank-line fixture created
  no dataset. Explicit confirmation created dataset
  4055dc6772ee4dbbbf2b7c2f81a6e4e5 with three records from original lines 1, 3 and 4.
  The native private export flow saved a ZIP whose complete manifest equals the
  saved dataset, including independently checked original/line/extracted hashes;
  raw JSONL was absent. Restarting both backend and rebuilt app reopened exactly
  the same manifest without reimporting; only one dataset exists and no trial ran.
  Evidence: /tmp/almg-jsonl-native-qa/ (rejected-ui.txt, review-ui.txt,
  dataset-ui.json, reopened-dataset-ui.json, export-review-ui.txt, verification.json,
  build/restart logs and test logs). Generated files remain outside Git.
- Verification: 397 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed, Flutter analysis and diff checks passed. Added JSONL tests cover original
  and line provenance, exact private export, stale review/changed source/consent
  rejection, unsupported fields, malformed encoding/nesting and bounded inputs.
- Remaining: resumable JSONL-specific preparation drafts and larger/streamed JSONL
  ingestion are not delivered by this bounded importer. Full streamed training,
  supervised planning/checkpoint recovery, broader mixing/incremental policies and
  larger-than-RAM verification remain open. Unchanged physical power/Windows and
  safe scratch-space blockers were skipped, without polling or deleting artifacts.
  Unrelated user changes, generated datasets, exports and weights are not committed.

P3-LMF-02 partial progress · restart-safe JSONL preparation drafts · 2026-11-20:
- [ ] P3-LMF-02 remains open. The local JSONL review now offers an explicitly
  confirmed saved preparation draft containing original bounded input bytes and
  the exact extraction review. A separate JSONL inventory reopens pending/completed
  drafts; nothing executes automatically. Explicit preparation reuses the stable
  draft ID as dataset ID and preserves file/line provenance and tokenizer policy.
- Saved input digests and implementation revisions reject tampered/stale pending
  drafts while preserving them for review. Dataset publication followed by a draft
  update failure recovers the same verified dataset rather than publishing another.
  Completed records verify the dataset manifest digest and reopen idempotently.
  Existing HTML/text preparation namespaces and already prepared datasets are
  unchanged; saved original inputs remain local and are not added to dataset exports.
- Local app verification: rebuilt native macOS ALMG against isolated fixture port
  28832. Saving one JSONL file/three text records created draft
  9beb3522e3d142e7903d5051dfd3d6bf in awaiting_preparation with no dataset. Moved the
  original synthetic file, restarted both backend and app, and reopened the exact
  pending record; no file picker or automatic publication occurred. Confirming
  Prepare saved JSONL inputs created dataset with the same ID and original bytes/
  source hash. Opening the completed draft again returned the identical dataset;
  exactly one dataset exists and no trial/training ran. Evidence:
  /tmp/almg-jsonl-draft-native-qa/ (review-ui.txt, draft-ui.json,
  reopened-draft-ui.json, dataset-ui.json, reopened-dataset-ui.json,
  completed-draft.json, verification.json and build/restart/test logs).
- Verification: 400 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed, Flutter analysis and diff checks passed. New tests cover reload, explicit
  consent, stable identity/idempotency, injected post-publication write failure,
  changed implementation and input tampering. Generated fixtures stay outside Git.
- Remaining: this is bounded JSONL recovery, not large/streamed JSONL ingestion.
  Full streamed training/planning/checkpoint recovery, broader mixing/incremental
  policies and larger-than-RAM acceptance remain open. Existing physical hardware,
  Windows and safe scratch-space blockers stayed open and were skipped without
  repeated polling. User edits, training artifacts and weights were preserved;
  no external collection, generated artifact commit or push.

See [PROJECT_TASKS.md](PROJECT_TASKS.md) for the existing implementation baseline and more detailed backlog.

## Model Training workspace design

**Implementation gate.** Finish and verify the P2 chat and project work before
replacing the training form. Launch into the Dashboard. The
Dashboard opens the Training workspace, Model Library, and Chat. Qwen chooses
from the text classifier and experimental text-to-image recipes.

### Desktop layout

```text
┌────────────────────── Model Training ────────────────────────────┐
│ ‹ Chat   Training sessions   ▾   + New task                      │
├──────────────────────────────────┬──────────────────────────────┤
│ Training conversation            │ Model creation               │
│                                  │ Support ticket classifier    │
│ You                              │ Awaiting approval            │
│ Classify support tickets into    │                              │
│ billing, account, and shipping.  │ ● Plan ready                 │
│                                  │ ○ Dataset                    │
│ Qwen                             │ ○ Training                   │
│ Which label should apply when    │ ○ Evaluation                 │
│ a ticket mentions two topics?    │ ○ Artifacts                  │
│                                  │                              │
│ Review dataset plan              │ Current stage · Plan         │
│ [Review proposal]                │ Labels, source, metric        │
│                                  │ [Review proposal]            │
│ [Describe your goal or reply ⬆]  │                              │
└──────────────────────────────────┴──────────────────────────────┘
```

- Give the timeline roughly 60% of the desktop workspace. Keep the composer
  anchored below the timeline and let each pane scroll independently.
- Keep the task name, current status, and next action visible at the top
  of Model creation. Expand the current stage by default and let the user
  open past stages. At narrow widths, switch between **Conversation** and
  **Model creation** using tabs, with an indicator for a pending approval.
- Reuse the chat composer, Markdown rendering, and streaming behavior.
  Keep a distinct session for each training task. Users can return to a
  previous task by name and see its transcript, approvals, and results.
- Make approvals explicit labeled buttons. Permit keyboard navigation and
  announce status changes to assistive technology. Use text with any status color.

### Conversation and approval flow

ALMG's locally configured Qwen model interprets the goal, asks clarifying
questions, and drafts a plan. Conversational drafting is read-only. A chat
message such as “go ahead” keeps the conversation moving. The corresponding
work begins only when the user presses the approval button for the pending
proposal. Show that same proposal in the conversation and the model panel.

| Task | What the approval shows |
| --- | --- |
| Save plan | Model goal, task type, labels, sample inputs and outputs, dataset requirements, and target metric |
| Prepare dataset | Generate synthetic examples or import a named file. Show the format, target count, and planned checks |
| Search the web | Exact queries, provider, domains or scope, and result limit. Request a separate approval before fetching full pages, with URLs and limits shown |
| Finalize dataset | Preview, class balance, duplicates, missing labels, split strategy, and the dataset version that will be used |
| Start training | Recipe, dataset version, parameters, estimated time and resources, and whether the task waits for idle time and AC power |
| Evaluate or improve | Separate validation and held-out test data. Show the proposed metric, retry limit, and any data or parameter changes before a new run |
| Run simulation | Candidate, simulator, scenarios, acceptance criteria, and retry limit |
| Export | Model, dataset, and report files, their formats, and destination |

Each proposal offers **Approve**, **Request changes**, and **Decline**. Editing
the scope creates a new revision that requires approval. Save decisions with
the task, including the scope and timestamp. Enforce the approval in the
backend before starting work. Reopening a task restores the current approval
state, and repeated clicks on Approve must not start duplicate work.

### Model creation panel

- [ ] Use chat as the primary training interface. In the adjacent work pane,
  show what ALMG is doing now, including the current action, its status,
  and progress when measurable. Update the pane as planning, dataset
  preparation, training, and evaluation advance. When work is waiting for an
  answer, approval, or resource, show what it needs.
- **Plan** shows the goal, labels, success criteria, approved scope, and the
  latest plan revision. Unanswered questions link to the conversation.
- **Dataset** shows the source mode, preview rows, example counts by label,
  duplicates, source provenance, and dataset version.
- **Training** shows the selected recipe, hardware checks, current step,
  elapsed time, and recent logs. Offer cancellation while running and show
  pause or resume only when the recipe supports checkpoints. For an idle job,
  explain the condition it is waiting for.
- **Evaluation** shows the target and measured scores, per-label results, and
  representative mistakes. Mark validation and held-out test scores separately.
  Any retry proposal links back to the results that prompted it.
- **Artifacts** lists the exported model, dataset, and report with their paths
  and file sizes. Include a way to open the output folder.

Use the same persisted job state in both panes. Show specific waiting,
running, completed, cancelled, and failed states. If the backend disconnects,
retain the conversation and last known job data and refresh when it reconnects.

### Implementation and acceptance

- [ ] Add the two-pane Flutter workspace and narrow-window tabs. Verify that
  switching panes or returning to Chat preserves the training task.
- [ ] Add persisted training sessions, proposal revisions, and decisions to
  the Python backend. Test declined, edited, stale, and duplicate approvals.
- [ ] Wire up the text-classifier flow from dataset preview through export.
  Verify that web access waits for explicit approval of the exact scope, and
  that an approved training run uses the selected dataset version.
- [ ] Verify onboarding, backend reconnect, cancellation, failure recovery,
  and successful export from the workspace. Test keyboard navigation at
  desktop and narrow widths.

### Using generated models

- [ ] Build the Model Library and **Run Model** screen first. Discover
  previously generated candidates and releases from saved jobs and artifacts.
  Show model name, project, recipe, creation date, and candidate or release
  status. Track the files needed for inference, including diffusion weights
  stored separately from exported metadata.
- [ ] Provide a persistent **Model Library** across projects. Add generated
  models to it when they are ready for inference and group their versions
  under one model entry. Show each version's evaluation and release status.
- [ ] Let users name and tag models, search by name or use case, and filter
  by project, model type, and deployment target. Keep each version linked
  to its training run, evaluation results, and hardware validation status.
- [ ] Let users open a specific version from the library after restarting
  ALMG, run it on fresh inputs, and access its export and usage instructions.
  Show any missing runtime or dependency and what is needed to run it again.

- [ ] Make practical use of the generated model part of completing a project.
  Ask in chat where the user wants to run it and what real inputs and outputs
  they expect. Use those answers to plan inference, testing, and delivery.
- [ ] Let users reopen a saved model and run new inputs in ALMG after
  training. Use input controls and results appropriate to the model. For
  workflows that involve multiple inputs, offer batch inference where supported.
- [ ] For external use, deliver the model in a format supported by the target
  runtime with its dependencies, input and output formats, setup instructions,
  and a runnable inference example. Report which target checks passed and
  which are pending.

- [ ] When the user specifies a deployment target, include hardware
  validation in the testing plan. Run the exported candidate on the target
  or a connected test device with the matching configuration. Check that it
  loads, produces expected outputs on representative inputs, and meets
  agreed latency and memory limits. Record the device, runtime, artifact
  version, and measured results.
- [ ] Show hardware validation status separately from model evaluation and
  simulation. If compatible hardware is unavailable, keep the evaluation
  results visible and mark hardware validation as pending. For physical
  systems, include bench or hardware-in-the-loop tests where the use case
  calls for them.
- [ ] When a trained candidate is ready for inference, open its **Model
  preview** in the work pane. Let the user run the candidate directly in ALMG
  before export. Match the controls and results to the recipe, such as text
  and predicted labels for classification, or a prompt and generated image
  for image generation. Keep the training conversation accessible.
- [x] Add a **Model preview** chat for each trained candidate. The user enters
  representative inputs, and the generated model produces the replies using
  the selected recipe. A classifier shows its predicted label.
- [x] Show the candidate version, evaluation target, measured score, and
  expected inputs alongside the preview. Let users run multiple examples
  and review the results before approving release.
- [x] Enforce the release gate in the backend. A candidate must meet its
  evaluation target, return at least one successful preview result, and
  receive explicit user approval before ALMG exports it as a released model.
  Training a replacement candidate resets its preview and approval.
- [x] Test the gate with an untested candidate, a candidate below its
  evaluation target, and a successful candidate. Verify inference uses the
  trained candidate and that the released model reproduces its predictions.

### Text-to-image recipe

ALMG's first image generator learns from local synthetic prompt and image pairs.
It creates 48 × 48 RGB images of up to three colored circles, squares, or triangles, with
optional left, center, or right placement. ALMG fits the shape and color weights
from scratch. Some shape and color combinations are held out for evaluation.
The preview and approval gate applies before export. The exported JSON weights
are usable by a pure Dart inference class. Android and iOS application
integration and on-device validation are pending.

### Training projects and artifacts

- Training conversations require an existing Chat project. Select a project in
  Model Training, then start a conversation or reopen one from its history.
- ALMG saves training records, dataset rows, completed candidates, and recent
  preview results locally. A saved dataset or candidate can be reopened after
  a backend restart. An interrupted active operation requires a new run.
- After approval, ALMG exports the image model as versioned JSON weights and
  the text classifier as Joblib, alongside JSONL dataset rows and a JSON
  evaluation report. The model path can be copied from Model creation.

### Web datasets for text-to-image training

- [ ] In the Training screen, propose image search queries from the user's goal. Show the provider, source scope, and result limit for approval before searching.
- [ ] Present candidate image URLs for a separate download approval. Show the source, available caption and license information, and collection limits. Collect supported image files relevant to the training goal.
- [ ] Save a local dataset with each image's caption, source URL, license, and checksum. Validate file types and dimensions, deduplicate images, and keep related images together when splitting training and evaluation data.
- [ ] Show collection progress, rejected files, subject coverage, and sample image-caption pairs. Let the user review the dataset before approving training.
- [ ] Train an image generator from scratch on the approved dataset. Evaluate it on unseen captions and subjects in Preview, and verify the exported model on Android and iOS before release.

## Future model generation recipes

Each row describes a planned recipe family and example goals for the Training conversation. Multiple use cases can use the same trainer.

| Recipe family | Example use cases |
| --- | --- |
| Text classification | Route tickets, detect spam, identify intent, tag topics, analyze sentiment, detect language, categorize documents, moderate content |
| Text extraction and matching | Extract entities and dates, redact personal information, extract contract clauses, produce structured JSON, match duplicate records, link mentions to known entities, extract relationships |
| Text and code generation | Draft replies and product descriptions, summarize reports, rewrite in a brand voice, translate, correct grammar, answer questions about supplied passages, generate code or tests, learn tool calls from examples |
| Search and retrieval | Search by meaning, retrieve passages, rerank results, find similar documents, match queries to products, find images by description |
| Document AI | Recognize printed and handwritten text, extract invoice and receipt fields, analyze page layout, extract tables, classify scanned forms, answer questions about document images |
| Image recognition | Classify images, assign multiple tags, detect and count objects, segment regions, estimate pose, detect manufacturing defects, find similar products |
| Image generation and editing | Generate images from prompts, adapt to a visual style, create product scenes, edit from instructions, replace backgrounds, fill missing regions, restore and upscale photos |
| Video understanding | Recognize actions, track objects, detect events, locate relevant clips, caption video, summarize footage, classify events using audio and video |
| Video generation | Generate short clips from prompts, animate still images, interpolate frames, upscale footage |
| Speech and audio | Transcribe or translate speech, identify speaker turns, detect wake words, classify sounds and music, remove noise, separate sources, synthesize narration, generate sound effects |
| Tabular classification and regression | Predict churn or returns, categorize leads and claims, estimate delivery times, predict order value or repair costs, estimate energy use |
| Time-series forecasting | Forecast sales, demand, inventory, staffing, traffic, energy consumption, or equipment readings, including forecasts across related products or locations |
| Anomaly detection and maintenance | Flag unusual transactions, detect sensor faults or unexpected sales changes, identify visual defects and dataset outliers, predict time to equipment failure from maintenance history |
| Recommendations and ranking | Recommend products, articles, courses, music, or jobs, rank items, suggest related items, personalize feeds |
| Clustering and topic discovery | Segment customers, discover feedback themes, group similar images and documents, identify patterns in unlabeled data |
| Graph learning | Classify nodes or graphs, predict missing links, recommend related entities, identify communities |
| Geospatial and remote sensing | Classify land cover, detect changes in satellite imagery, map roads and buildings, identify crop stress, estimate traffic from road sensors |
| 3D and spatial AI | Estimate depth, classify point clouds, segment 3D scenes, reconstruct objects from images, generate 3D assets |
| Multimodal AI | Caption images, answer questions about charts or screenshots, match images and text, classify products from photos and descriptions |
| Decision-making and control | Learn game strategies, adapt simulated robot movements, optimize simulated warehouse routing, learn scheduling policies, choose recommendation strategies from feedback |
| Model adaptation and compression | Adapt to a domain or language, learn from preference pairs, distill a large model, train with quantization for device deployment |
| Data imputation and synthetic data | Fill missing fields or sensor readings, generate synthetic tabular records, augment labeled training examples, generate test data from a schema |
| Event-time prediction | Estimate time until subscription cancellation, equipment failure, or a service milestone using event histories and incomplete observations |
| Scientific and engineering prediction | Estimate material properties, approximate engineering simulations, classify astronomical imagery, predict environmental measurements |

Include **Answer questions from my documents** in the picker. Route goals about
accessing current documents to a retrieval workflow. Offer embedding or reranker
training when users have query and relevance examples, and assistant fine-tuning
when they have examples of the intended response behavior.

### Qwen3.8 recipe selection

- [ ] Make **Automatic (Qwen)** the default when a user describes a model
  in chat. Use the configured local Qwen3.8 planner to infer the task and
  choose a recipe at runtime from ALMG's registry. The user can start with
  any plain-language goal. Keep the planner checkpoint configurable.
- [ ] Drive routing and follow-up questions from the goal, conversation, and
  recipe metadata. Register new recipes with their capabilities and trainer
  entry points so Qwen can consider them without adding intent keywords or
  use-case-specific routing branches. The backend dispatches the validated
  recipe ID to its registered trainer.
- [ ] Give Qwen the user's goal, expected output, available data profile,
  deployment target, and recipe metadata. Each registry entry defines its ID,
  supported tasks, required dataset fields, compatible checkpoints and
  hardware, evaluation metrics, export formats, and availability.
- [ ] Have Qwen return a structured proposal with the recipe ID, why it fits,
  required inputs, unresolved questions, and any viable alternative. If a
  missing detail would change the choice, ask a focused question. For example,
  distinguish assigning one label to an image from locating multiple objects
  in it.
- [ ] For each use case, have local Qwen ask for the details it still needs
  to select or configure the recipe. Ask in chat and show a few selectable
  options relevant to the request. Explain what each requested detail helps
  decide. Reuse answers already given. Accept custom answers and request a
  file, sample input, or desired output when that is the missing detail.
  Record each answer and have Qwen reassess the recipe and its settings.
  For example, an image request could offer **Label the whole
  image**, **Locate objects**, and **Outline regions**.
- [ ] Validate the proposed ID, dataset schema, hardware, and export
  compatibility in the backend. If the recipe is planned or incompatible,
  show its status and explain what is missing. When no registered recipe
  fits, explain the unmet capability and show any viable alternatives.
  Allow the user to review or
  override the proposed recipe before approving the run.
- [ ] Save the selected recipe version, planner checkpoint, selection rationale,
  dataset version, and final settings with the training session. Apply the
  existing approvals for data collection and training.
- [ ] Verify routing with representative requests. Route support ticket labels
  to text classification, next month's sales to forecasting, and a count of
  visible products to object detection. Verify that ambiguous requests prompt
  for the missing detail and unavailable recipes cannot start a run.

### Qwen-led model development

- [ ] Turn the user's goal into concrete input and output examples. Reuse
  confirmed project decisions and ask focused questions with selectable
  answers when a missing detail would change the plan.
- [ ] Inspect shared files locally. Propose column and label mappings and
  show examples of missing labels, conflicting categories, and gaps in
  coverage. Queue ambiguous or underrepresented examples with suggested
  labels the user can correct in place.
- [ ] Draft acceptance criteria and saved Model Preview tests from the user's
  priorities. Recommend a baseline or quick trial and use measured results
  to propose a full run or revise the plan.
- [ ] Build the candidate through ALMG's registered tools and show progress
  in the work pane. Compare candidates on the same tests, show representative
  failures, distinguish measured findings from hypotheses, and propose
  targeted changes. Save confirmed decisions and compare newly supplied data
  with the project's previous dataset when the user returns.

### Worked example · Drone collision avoidance and free roam

This example illustrates how the general workbench adapts to a user request.

- [ ] Ask in chat for the airframe configuration, flight controller and
  firmware, sensor inventory and placement, available compute, and existing
  control logic. Clarify what free roam means, the intended operating
  environment, the expected model inputs and outputs, and the desired
  behavior when a sensor drops out or the operator takes over.
- [ ] Have Qwen select a compatible recipe and simulator from the registry,
  identify missing data, and propose a training and simulation plan based on
  the user's instructions. Present the scenarios and pass criteria for
  review before running the approved plan.
- [ ] Train and simulate the candidate in ALMG. Show progress and replayable
  results for obstacle encounters, free roam boundaries, sensor dropout,
  and operator takeover. Compare recorded outcomes with the agreed criteria
  and show failed scenarios with proposed changes before another run.
- [ ] When the candidate meets the agreed simulation criteria, present it
  in Model Preview alongside the simulation report. Include the compatible
  flight controller or companion runtime, input and output interface,
  integration instructions, and remaining bench and controlled flight
  validation steps. Record simulation and hardware validation separately
  and apply the existing release approval before export.

## Dashboard and project navigation

Implement the Dashboard after Model Library discovery and inference work
for existing models.

- [ ] Show **Training activity**, **Recent models**, and **Recent chats**
  on launch, with a link to the full Model Library. Refresh active training
  status while the Dashboard is visible.
  Verified on macOS: the grid showed the latest model state, and the separate
  chat list reopened the exact saved transcript in its project. Training
  activity and recent model rows with automatic refresh are pending.
- [ ] Open the exact training session from its row with progress and pending
  actions. Open **Run Model** for the selected model version and restore the
  selected chat with its project context.
- [x] Provide **Add Project** on the Dashboard. Collect a project name and a
  local directory, save both, and offer **Open Model Training** with the new
  project selected.
  Verified on macOS: naming a project and choosing a folder saves both values
  and adds the card to the grid. The post-create **Open Model Training**
  action opened a fresh conversation with the new project selected.
- [ ] Validate that the selected directory is writable before training.
  Store datasets, checkpoints, models, and reports for new runs in an
  ALMG-managed subfolder. Resolve existing runs at their recorded locations
  and allow users to reconnect a moved directory in Project Settings.
- [ ] Provide **New Model Training** and **New Chat** on the Dashboard.
  Open a blank training conversation in the selected project, or show the
  project picker when needed. Open a blank chat with the selected project's
  context when available. Provide a way back to the Dashboard and show new
  activity after it is saved.
- [ ] Verify that each Dashboard row restores the exact item after relaunch.
  Create a project with a chosen directory, train a model, and verify that
  the generated assets are stored there and the session can be reopened.

## Future enhancements

### Release milestones

- [ ] **Usable macOS release (6–10 weeks).** Verify the workbench on a clean
  install from data import through training, evaluation, preview, export,
  and hardware validation on one supported target. After relaunching ALMG,
  find a model trained before the library was added and run a fresh input.
  Use the delivered instructions to run the
  exported model on the supported target.
- [ ] **Broader workbench release (4–6 months).** Verify the same workflow
  across substantially different model types and deployment targets.

Estimates are cumulative planning ranges for one full-time developer.

### First priorities

- [ ] **Dataset health checks.** Before training, show missing labels, invalid
  rows, underrepresented classes, and duplicate examples within or across
  splits. Link each finding to the affected examples so users can correct
  them and rerun the checks.
- [ ] **Baseline comparison.** Evaluate the candidate and a recipe-appropriate
  baseline, such as a simple predictor or the original pretrained model, on
  the same held-out data with the same metrics. Show changes in scores and
  examples where the candidate improved or regressed.
- [ ] **Saved test cases in Model Preview.** Let users save a representative
  input and its expected output or acceptance criteria. Keep the cases with
  the project and let users rerun them against each candidate. Show pass,
  fail, or review-needed results and flag regressions from the previous
  candidate in the work pane.

### Additional enhancements

- [ ] **Review and correct predictions.** Let users edit a prediction in
  Model Preview and choose whether to save the correction as a test case or
  include it in the next training dataset.
- [ ] **Run estimates and quick trials.** Before training, estimate memory,
  disk space, and runtime. Offer a short trial to verify that the dataset and
  training setup work before the user starts a full run.
- [ ] **Experiment history.** Compare candidates by dataset version, recipe,
  settings, evaluation results, model size, and inference speed. Let users
  duplicate a run and edit its settings.
- [ ] **Batch inference in ALMG.** Run a trained model on a compatible CSV,
  image folder, or audio collection. Export predictions with enough input
  identifiers to match each result to its source.
- [ ] **Deployment compatibility checks.** Let users specify the target
  platform and runtime, show compatible export formats, and run a sample
  prediction with the exported artifact when the target runtime is available.
