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
- [ ] Validate the Windows build and a CPU training run on Windows. Evaluate GPU support and decide whether planning runs locally on Windows or uses a paired Mac.

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
