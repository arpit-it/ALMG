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

P3-LMF-02 partial progress · bounded complete-split reader integrity sessions · 2026-11-20:
- [ ] P3-LMF-02 remains open. Complete streamed diagnostic evaluation now uses a
  bounded split iterator with full window/source/tokenizer/overlap validation at
  both split boundaries, rather than rehashing every artifact for every small
  batch. File size, modification/change timestamps and inode guards cover all
  eight immutable data/manifest files before/after each page and after scoring.
  There is no global trusted cache; callers must exhaust the iterator before
  publishing complete metrics. Interactive batch review retains its full checks.
- SQL pages retain at most seventeen rows for sixteen model windows, share the
  existing target/mask/provenance formatter and preserve deterministic split order.
  Source changes at initial verification, between pages, after the final yielded
  page or at final full-hash verification reject complete evaluation. No report is
  published on failure. Report metrics record this boundary verification policy;
  full target weighting and zero held-out optimizer updates remain unchanged.
- Local app verification: rebuilt and ran native macOS ALMG on isolated fixture
  port 28833. Explicit diagnostic confirmation created report
  a8fafa21a959482f8d0ef89ec84a51cc over all 764 validation and 702 test windows /
  11,852 and 10,908 targets in 48 and 44 batches. Instrumented fixture observed
  six full binding checks for the diagnostic (two each for validation/test plus
  the initial/final training batch), versus 94 calls with the prior per-batch
  path. This verifies scan-count reduction, not a wall-time benchmark. Independent
  unpadded CPU evaluation matched all target/correct counts and loss within 1.7e-7.
  All 18 source fixture files stayed byte-identical; saved native report reopened
  exactly without rerunning; only one diagnostic JSON and no model were saved.
  Evidence: /tmp/almg-stream-scan-native-qa/ (report-ui.json,
  reopened-report-ui.json, binding-count-verification.json, verification.json,
  binding-checks.jsonl, build and regression logs); generated evidence is untracked.
- Verification: 403 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed, Flutter analysis and diff checks passed. New tests compare iterator and
  existing paged batches exactly, assert constant boundary checks, reject mid-scan
  and final-page changes and demonstrate final full hashes reject corruption even
  with the stat guard mocked unchanged. Existing consent/source-change tests pass.
- Remaining: larger-than-RAM acceptance, synchronous evaluation recovery, full
  streamed training/planning/checkpoint binding and broader mixing/incremental
  policies stay open. Unchanged hardware/Windows and scratch-space blockers were
  skipped without polling. No external collection, artifact/weight changes or push.

P3-LMF-02 partial progress · summary-only streamed approach planning · 2026-11-20:
- [ ] P3-LMF-02 remains open. Completed streamed windows now connect to the
  existing local planner and registered decoder recipe catalog. Planning sends
  only the goal, window/source/tokenizer/overlap IDs and revisions, record/window/
  target counts and recipe contracts; no original text, token arrays, source names
  or permission notes are included. The planner can recommend from-scratch,
  fine-tuning, distillation or retrieval, with an explanation and registered recipe.
- Exact reviewed window/source bindings, recipe availability and planning code are
  checked before/after planning. Plans are revisioned, immutable and reopenable in
  a separate namespace. Explicit acknowledgment rechecks source evidence and saves
  a separate revision-bound receipt; closing saves no acknowledgment. Both plan
  and receipt remain non-executable with training/release approval false. Existing
  executable-trial approval rejects these plans. Full streamed training remains
  visibly unavailable; acknowledgment is not consent to run a model.
- Local app verification: rebuilt native macOS ALMG on fixture port 28834 using a
  clearly labeled scripted_local_fixture planner (not a live Qwen inference).
  Submitted a synthetic goal, inspected captured summary-only planner input, and
  reviewed plan a1080644a3dc4c2d947f7513b4c4651d. Closing created no acknowledgment.
  Restarted both backend and app, reopened the identical saved plan without another
  planner request, then explicitly acknowledged it. Native receipt confirmed all
  execution/training/release flags false. No trial/model was created, and all 18
  source fixture files remained byte-identical. Evidence:
  /tmp/almg-stream-plan-native-qa/ (goal-ui.txt, plan-ui.json, planner-input.json,
  reopened-plan-ui.json, receipt-ui.json, verification.json and build/restart logs).
- Verification: 406 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed; Flutter analysis and diff checks passed. Added tests cover summary-only
  payloads, registration/approach validation, missing consent, changed evidence,
  saved-plan tampering, idempotent acknowledgment and rejection by trial approval.
  Existing small-dataset planning and recipe regressions remain passing.
- Remaining: live Qwen streamed-plan selection is not established by the scripted
  fixture. Full streamed trial execution, scheduling, checkpoint cursor recovery,
  broader mixing/incremental policies and larger-than-RAM acceptance remain open.
  Physical power/Windows and safe scratch-space blockers stayed open and were
  skipped without unchanged polling. No external collection, weights/artifact
  modification, generated artifact commit or push; unrelated user edits preserved.

P3-LMF-02 partial progress · bound live-Qwen streamed planning evidence · 2026-11-20:
- [ ] P3-LMF-02 remains open. New streamed approach plans bind the canonical
  planner-adapter input (system instructions plus summary-only context), registered
  recipe catalog and validated JSON result to SHA-256 fingerprints. Request
  mutation during planning rejects publication. A provider identifying as local
  Qwen must report a loaded model name and a verified 64-hex weights revision;
  missing/unloaded/unverified identity rejects without saving a plan. Existing
  version-one plans without these additive fingerprints remain readable.
- Local app verification closed the previous synthetic native workflow's live
  Qwen verification gap: rebuilt native macOS ALMG on isolated fixture port 28835
  used the already downloaded, verified mlx-community/Qwen3.8-27B-4bit checkpoint,
  without a scripted planner, download or weight modification. A synthetic offline
  research goal produced plan 8c165389ae0d4a2d80772bdd4dba8417 recommending
  from_scratch via registered decoder_from_scratch. Saved provider was local_qwen,
  loaded=true with verified weights revision
  9a6194da35d6e590c38d8ce1076fc48e86197d45ce21e38dddf5180a5cc4f107.
- Captured adapter request and actual Qwen JSON result independently matched the
  saved fingerprints; input contained only the allowed dataset counts/evidence
  revisions and recipe catalog, with no source text or token arrays. Explicit
  acknowledgment kept execution/training/release flags false; no trial/model was
  created. Backend/app restart reopened the identical saved plan without another
  inference request. All 18 source fixture files stayed byte-identical and all
  checkpoint file fingerprints stayed unchanged. The isolated inference process
  was restarted to release its loaded model while preserving weights/artifacts.
- Evidence: /tmp/almg-live-stream-plan-native-qa/ (plan-ui.json,
  reopened-plan-ui.json, planner-request.json, planner-result.json, receipt-ui.json,
  verification.json, weights-before.json and build/restart/test logs). Generated
  plans, traces, datasets and model files are excluded from Git.
- Verification: 407 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed, Flutter analysis and diff checks passed. Tests verify exact request/
  catalog/result digests, mutated-request rejection, verified local-Qwen identity
  requirements and legacy plan readability, alongside existing approval rejection.
- Remaining: this verifies approach planning on one synthetic dataset/goal, not
  streamed trial execution, model quality, scheduling or checkpoint cursor recovery.
  Broader mixing/incremental policies and larger-than-RAM acceptance remain open.
  Unchanged physical power/Windows and safe scratch-space blockers were skipped
  without polling. User changes and training artifacts were preserved; no push.

P3-LMF-02 partial progress · resumable streamed JSONL text preparation · 2026-11-20:
- [ ] P3-LMF-02 remains open. Stored local sources now offer a separate confirmed
  streamed JSONL preparation path, removing the small importer’s 16-record limit.
  The source picker accepts .jsonl alongside .txt. Each nonblank UTF-8 physical line
  must be an object containing exactly one string text field; unknown/duplicate
  fields, malformed JSON, invalid Unicode, empty text and unsupported controls/
  tokenizer limits reject the current transaction. Original lines remain bounded
  to 64 KiB; processing uses the established bounded byte/line transaction budgets.
- Extracted bodies use existing NFC/whitespace normalization, global exact dedup
  and canonical normalized-text hash split buckets. The immutable shared index
  retains original source hash/bytes, first line, byte offset, raw-line hash and
  occurrence count. Blank lines are counted. Cursor/rows commit together and resume
  explicitly after restart; malformed batches roll back while preserving earlier
  progress. The new worker has its own implementation binding; existing plain-text
  preparation implementation and previously saved indexes are unchanged. Shared
  record review, byte analysis and private export consume the resulting index.
- Local app verification: rebuilt native macOS ALMG on fixture port 28836. Uploaded
  183,180-byte synthetic JSONL source b6562b4160b34b8db0c4fdc2c816177e through the
  native picker/storage confirmation. Canceling extraction created no index.
  Confirmed preparation of index f258e2cc52c249c19c4bce65488849eb paused at 100 lines,
  99 unique records and byte 28,316 (fixture used 100-line steps for deterministic
  pause verification). Backend/app restart reopened that exact committed cursor;
  explicit resume completed all 603 lines: 601 unique, one duplicate, one blank;
  split counts train 489 / validation 53 / test 59. Independent inspection verified
  every extracted body, canonical group hash, split, line, offset and raw-line hash;
  original bytes were unchanged. Native record review showed extracted bodies.
- Native private export saved exact manifest/database copies. A standalone restored
  copy read successfully without raw JSONL; source hash, JSONL method and line
  provenance survived. No trial/training ran. Evidence:
  /tmp/almg-stream-jsonl-native-qa/ (source-ui.json, preparation-consent-ui.txt,
  paused-index-ui.json, reopened-index-ui.json, completed-index-ui.json,
  records-ui.txt, export-review-ui.txt, export-completed-ui.txt, verification.json,
  build/restart logs). Generated source/index/export copies are excluded from Git.
- Verification: 410 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed, Flutter analysis and diff checks passed. Added tests cover explicit
  consent, pause/reload/resume, extraction/dedup/lineage, private export/byte-analysis
  compatibility, malformed-batch rollback, schema/Unicode/control/size rejection
  and unchanged legacy plain-text behavior.
- Remaining: larger-than-RAM acceptance is not established by this small fixture;
  that scratch-space blocker remains open. Full streamed training/scheduling/
  checkpoint recovery and broader mixing/incremental policies also remain open.
  Unchanged power/Windows blockers were skipped. No external collection, weights/
  training artifact changes, generated artifact commit or push; user edits preserved.

P3-LMF-03 partial progress · approved byte-level BPE comparison experiments · 2026-11-20:
- [ ] P3-LMF-03 remains open. Independent tokenizer work now uses the verified
  small-dataset path while P3-LMF-02's larger-than-RAM/scratch-space criterion stays
  open. A separate byte-level BPE engine deterministically fits adjacent byte-pair
  merges on explicitly approved training records only, with a configurable 256–512
  vocabulary cap, minimum pair frequency two and lexicographic token-ID tie breaks.
  The fixed 256-byte alphabet covers valid UTF-8; merges never cross documents.
  Each unique training record contributes once; mixture weights are not expanded.
- The bounded experiment supports at most sixteen documents / 4096 UTF-8 bytes per
  sample, saves exact dataset/config approval evidence and training-document hashes,
  and compares fixed-byte/BPE token counts, efficiency, unknown-token counts and NFC
  round trips independently for train/validation/test. Held-out records are encoded
  but never fitted. Versioned tokenizer/manifest files are immutable, checksum-bound,
  reloadable and privately exportable; learned merges may encode private phrases,
  which the confirmation/export UI discloses. Original dataset/tokenizer files and
  all existing model tokenizer contracts are preserved.
- Model training with these experiment artifacts is deliberately unavailable;
  incompatible vocabularies/configurations and legacy model-tokenizer loading are
  rejected. A learned vocabulary over 256 entries requires a future compatible
  architecture, and no model-pretraining integration or special tokens are claimed.
- Local app verification: rebuilt native macOS ALMG on fixture port 28837 with a
  five-record multilingual dataset. Canceling fitting created no experiment.
  Explicit training-split approval produced experiment
  2502ea1037e14beca625dbcb6a7a2767: 64 merges / 320 vocabulary entries from three
  training records. All five records round-tripped. Repetitive synthetic training
  text used 661 fixed-byte tokens versus 15 BPE tokens; validation stayed 127/127
  and test 175/175. These sample-specific counts are not general compression or
  model-quality evidence. Independent checks recounted every split and verified
  fitting hash/artifact against training records only; dataset files stayed exact.
- Native private ZIP export contained exactly the saved tokenizer and manifest,
  without dataset documents or weights. Exported tokenizer restored and round-
  tripped unseen résumé/Japanese/Hindi/emoji text. Backend/app restart reopened the
  identical experiment without refitting. No model trial or model was created.
  Evidence: /tmp/almg-byte-bpe-native-qa/ (fitting-consent-ui.txt, experiment-ui.json,
  reopened-experiment-ui.json, export-consent-ui.txt, verification.json and build/
  restart/test logs). Generated artifacts remain outside Git.
- Verification: 413 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed; Flutter analysis and diff checks passed. Tests cover golden merge IDs,
  deterministic fitting, unseen Unicode, training-split isolation, malformed IDs/
  merges/config, stale review/consent, checksum/reload/export and pretraining rejection.
- Remaining: plain BPE, Unigram, special-token definitions, larger/streamed fitting,
  generated-model compatibility and saving the trained BPE configuration with a model
  remain open. P3-LMF-02 and prior hardware/Windows/scratch-space blockers stay open
  and were skipped without repeated checks. No downloads, weight/training-artifact
  modifications, generated artifact commits or push; unrelated user edits preserved.

P3-LMF-03 partial progress · character BPE with explicit coverage gaps · 2026-11-20:
- [ ] P3-LMF-03 remains open. Tokenizer experiments now also support character-
  alphabet BPE: its sorted NFC codepoint alphabet and deterministic pair merges
  are learned exclusively from approved training records, under a configurable
  32–512 vocabulary cap. Unknown held-out characters reject encoding without
  adding vocabulary, refitting, substitution or an implicit unknown special token.
  The fixed-byte BPE path remains separately available with complete byte coverage.
- Split comparisons report encoded/total documents, uncovered codepoint counts,
  character coverage and token efficiency only over encodable records. A split
  with no encodable records has unavailable token counts/ratios and a false full-
  split round-trip flag; training coverage is not presented as held-out coverage.
  Both artifact types use checksum-bound manifests, separate approval/config
  evidence, strict reload/export and model-training-disabled policy. Existing
  version-one byte-BPE artifacts/configurations remain readable without rewriting.
- Local app verification: rebuilt native macOS ALMG on fixture port 28838, preserving
  the copied multilingual dataset and legacy byte-BPE artifact. Canceling character
  fitting created no new experiment. Explicit 128-cap approval created experiment
  05f676b60dfa47aab9d5efb1e7e1a9e6 with 26 alphabet entries + 41 merges = 67 tokens.
  Three training records round-tripped (661 byte tokens / 12 character-BPE tokens).
  Validation/test each had zero encodable records, 56/112 uncovered characters and
  unavailable efficiency ratios, displayed explicitly in the native comparison.
  This repetitive fixture does not establish general compression or model quality.
- Independent checks verified the training-only alphabet/artifact, all coverage
  counts and eligible-only denominators. Native private ZIP restored successfully
  and round-tripped a novel combination of known multilingual training text;
  uncovered Unicode still rejected without changing the vocabulary. All five
  dataset/legacy-byte-artifact files stayed byte-identical. Backend/app restart
  reopened both the legacy byte-BPE report and new character-BPE report exactly,
  without refitting; no model training ran. Evidence:
  /tmp/almg-character-bpe-native-qa/ (fitting-consent-ui.txt, experiment-ui.json,
  comparison-ui.txt, export-consent-ui.txt, reopened-experiment-ui.json,
  legacy-byte-ui.json, verification.json and build/restart/test logs).
- Verification: 416 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed; Flutter analysis and diff checks passed. New tests cover golden Unicode-
  alphabet merge IDs, NFC round trips, immutable unknown-character rejection,
  invalid alphabet/merge/config/artifact inputs, training-only fitting, coverage
  accounting, export and legacy byte-BPE compatibility.
- Remaining: Unigram, configurable special/unknown tokens, larger/streamed fitting,
  generated-model integration and tokenizer configuration saved with a model remain
  open. Prior dataset/hardware/Windows/scratch-space blockers remain open and were
  skipped without unchanged polling. No downloads, weight/training-artifact changes,
  generated artifact commits or push; unrelated user edits preserved.

P3-LMF-03 partial progress · bounded Unigram EM tokenizer experiments · 2026-11-20:
- [ ] P3-LMF-03 remains open. Approved tokenizer experiments now include a
  fixed-candidate Unigram language-model tokenizer. It retains all training NFC
  codepoints, selects frequent training substrings up to eight characters without
  crossing words/documents, fits normalized positive piece probabilities with five
  log-space forward/backward EM updates, and encodes using deterministic Viterbi.
  The fixed-vocabulary likelihood/EM formulation follows
  [Kudo 2018](https://aclanthology.org/P18-1007/); this bounded implementation does
  not claim SentencePiece artifact compatibility, vocabulary pruning or sampling.
- Fitting is training-split only, capped at sixteen documents / 4096 bytes per
  sample and 32–512 vocabulary entries. Saved artifacts include vocabulary,
  probabilities, normalization/method configuration, training revision and measured
  likelihood history; invalid probability/vocabulary/method records reject on load.
  Uncovered held-out characters retain explicit coverage gaps and cannot refit the
  alphabet. Comparisons now provide algorithm-neutral token/efficiency fields,
  retaining legacy BPE fields/readability. Model pretraining remains disabled.
- Local app verification: rebuilt native macOS ALMG on fixture port 28839. Cancel
  created no Unigram artifact; explicit 128-cap approval produced experiment
  8099a5828f104eb9a8ef8231afd2bc17 with 94 vocabulary entries from three training
  records. Marginal training log likelihood increased across five updates from
  -471.361505402112 to -219.69165278079112; probabilities were finite, positive
  and normalized. Training text round-tripped (661 byte tokens / 125 Unigram
  tokens). Held-out records remained unencodable with 56/112 uncovered characters
  and unavailable efficiency ratios. These synthetic results do not prove general
  compression, tokenizer quality or model-training readiness.
- Native private export restored vocabulary/probabilities and round-tripped a
  novel combination of supported multilingual text. Independent checks reproduced
  training-only fitting, likelihood evidence, coverage and token counts. All seven
  dataset/legacy-BPE files stayed byte-identical. Backend/app restart reopened the
  new Unigram and both legacy BPE experiment manifests exactly, without refitting.
  No model trial/training ran. Evidence: /tmp/almg-unigram-native-qa/
  (fitting-consent-ui.txt, experiment-ui.json, comparison-ui.txt, export-consent-ui.txt,
  reopened-experiment-ui.json, legacy-byte-ui.json, legacy-character-ui.json,
  verification.json and build/restart/test logs). Generated artifacts stay out of Git.
- Verification: 420 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed; Flutter analysis and diff checks passed. Tests compare forward/backward
  probabilities and expected counts against manually enumerated segmentations,
  check Viterbi output, deterministic EM/monotonic likelihood, normalized weights,
  Unicode/unknown handling, training-split isolation, invalid artifacts and export.
- Remaining: configurable special/unknown tokens, larger/streamed fitting,
  generated-model compatibility and tokenizer configuration saved with a model stay
  open. Prior hardware/Windows/scratch-space criteria stayed open and were skipped
  without unchanged polling. Completed isolated QA backends from this session were
  closed to release memory; current app and every artifact file were preserved.
  No downloads, weight modifications, generated artifact commits or push; unrelated
  user edits preserved.

P3-LMF-03 partial progress · explicit special-token IDs and lossy UNK policy · 2026-11-20:
- [ ] P3-LMF-03 remains open. Experimental byte-BPE, character-BPE and Unigram
  tokenizers now support validated pad/bos/eos/unk definitions. Distinct bounded
  ASCII marker labels are configurable through the API; native controls offer
  none, BOS/EOS/PAD with rejection, or BOS/EOS/PAD/UNK with explicit replacement.
  Reserved IDs are contiguous after actual base vocabulary entries, never collide
  with base IDs, and count toward the selected total vocabulary cap. Invalid roles,
  labels/collisions, replacement without UNK and insufficient capacity reject.
- Defined BOS/EOS are added at document boundaries; PAD is never auto-inserted.
  Literal marker strings in input remain ordinary text, not control IDs. Default
  decoding skips BOS/EOS/PAD while preserving UTF-8 byte continuity and never
  silently drops UNK. Replacement is opt-in, emits one UNK per uncovered NFC
  codepoint, does not refit the alphabet or edit original data, and is explicitly
  reported as lossy. Efficiency ratios and round-trip success use lossless records
  only; total token counts separately include configured boundary/UNK overhead.
- The versioned wrapper stores exact base artifact, definitions/IDs and encode/
  decode/unknown policies. Reload/export enforce ID/config integrity; all three
  legacy bare artifact types remain supported. Approval binds full configuration
  and original dataset. Model pretraining remains unavailable for these experiments.
- Local app verification: rebuilt native macOS ALMG on fixture port 28840. Cancel
  created no new artifact. Explicit Unigram + four-role replacement approval made
  experiment 66d2d600a9174ee9b9f0b1c86b3ccad3 with 98 entries under a 128 total cap:
  PAD 94 / BOS 95 / EOS 96 / UNK 97. Three training records round-tripped with 131
  tokens including six boundary tokens. Validation/test encoded 81/177 tokens with
  56/112 UNKs, each reported one lossy / zero lossless record, false round-trip
  status and unavailable efficiency ratios. Native display and independent counts
  confirmed these distinctions; no PAD was inserted.
- Native private ZIP restored exact IDs/policy. Backend/app restart reopened the
  wrapper and all three legacy experiment manifests exactly without refitting.
  All nine dataset/legacy artifact files stayed byte-identical; no model training
  ran. Evidence: /tmp/almg-special-token-native-qa/ (fitting-consent-ui.txt,
  experiment-ui.json, comparison-ui.txt, reopened-experiment-ui.json,
  legacy-byte-ui.json, legacy-character-ui.json, legacy-unigram-ui.json,
  export-consent-ui.txt, verification.json and build/restart/test logs).
- Verification: 424 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed; Flutter analysis and diff checks passed. Added tests cover custom labels,
  reserved-ID bounds, literal marker isolation, boundary opt-out, UTF-8-safe control
  skipping, explicit replacement/no refit, invalid/nested/tampered artifacts,
  total-cap admission, lossless-only efficiency, export and legacy compatibility.
- Remaining: larger/streamed fitting, generated-model compatibility and tokenizer
  configuration saved with a model stay open. Existing dataset/hardware/Windows/
  scratch-space blockers remain open and were skipped without unchanged polling.
  A completed prior QA backend was closed to free memory; current app and all
  artifacts remain available. No downloads, weight changes, generated artifact
  commits or push; unrelated user edits preserved.

P3-LMF-03 partial progress · source-bound model compatibility review · 2026-11-20:
- [ ] P3-LMF-03 remains open. Saved tokenizer experiments now offer native
  “Review model compatibility” with matching actual IDs, default 16 or maximum
  256 decoder vocabulary choices. The API accepts an exact integer vocabulary
  size in the registered bounded decoder's 4–256 range; invalid fields, booleans,
  stale reviews, changed dataset revisions and wrong training provenance reject.
- The version-1 read-only report restores the saved codec, counts all actual base
  and special IDs, checks model vocabulary equality and recipe capacity, and
  re-encodes every training/validation/test document. ID bounds and exact NFC
  round trips are recomputed from verified source records, not cached comparison
  claims. Explicit UNK replacement cannot satisfy lossless admission. Reports bind
  experiment/tokenizer/dataset revisions, selected vocabulary, implementation
  digests and exact per-split results; concurrent source changes reject publication.
- This is a compatibility review, not model integration or training authorization.
  Even a passing vocabulary/lossless review explicitly keeps pretraining, model
  training and release disabled. It initializes no weights, rewrites no dataset or
  experiment and requires the separate immutable model-tokenizer integration and
  explicit training approval before future execution can be enabled.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port
  28841. A saved character-BPE tokenizer matched 60 model IDs including PAD 57 /
  BOS 58 / EOS 59, and all five records round-tripped losslessly. Selecting 16 IDs
  reported vocabulary mismatch. Saved byte-BPE with 320 IDs against model maximum
  256 reported both capacity and mismatch blockers. Saved Unigram with matching
  98 IDs and replacement policy still reported validation/test lossless blockers
  (56/112 uncovered characters). Native cancel returned without creating work.
- Restarted backend/app, reopened the saved experiment and recomputed the native
  report: exact contents/revision matched. All 16 existing dataset/tokenizer files
  remained byte-identical; no model trial was created. Evidence under
  /tmp/almg-tokenizer-compatibility-native-qa/: matching-ui.json, mismatch-ui.json,
  oversized-ui.json, lossy-ui.json, cancel-ui.txt, restarted-matching-ui.json,
  verification.json and native build/restart logs.
- Verification: 429 Python tests passed with ALMG_METAL_TESTS=1, 34 Flutter tests
  passed; Flutter analysis and diff checks passed. Added coverage for special-ID
  accounting, lossless matching/mismatch, oversized vocabulary, lossy heldouts,
  invalid dimensions, stale/source/provenance failures, invalid emitted IDs,
  distrust of cached summaries, concurrent changes, reload and no writes/weights.
- Remaining: tokenizer adoption into an immutable reviewed dataset version,
  configuration saved/reloaded with a trained model, and larger/streamed fitting
  remain open. Existing hardware/Windows/scratch-space blockers were skipped.
  P3-LMF-01 is already complete. No external collection, downloads, generated
  artifact commits or push; unrelated user edits and all saved artifacts preserved.

P3-LMF-03 partial progress · reviewed tokenizer adoption and model persistence · 2026-11-20:
- [ ] P3-LMF-03 remains open. Saved experiments now offer confirmed “Use tokenizer
  in new dataset version.” Selection rejects oversized vocabularies, stale reviews,
  changed inputs and any split that cannot encode losslessly, including explicit
  lossy UNK replacement. It validates the codec against a deterministic training-
  split-only refit before atomic publication. Failed/stale publication removes
  temporary work and preserves existing datasets and experiments.
- New immutable datasets copy documents byte-for-byte and preserve splits, sources,
  permissions, mixture weights and prior derivation. A versioned model-use wrapper
  stores exact codec/merges or probabilities, control IDs, selection approval and
  original dataset/experiment revisions. Dataset readers verify that binding and
  lossless inputs; source-permission versions remain compatible. Selection grants
  no training approval. The existing separate bounded-trial confirmation binds
  the new dataset and starts fresh weights only after normal preflight/resource gates.
- Model bundles, step-50 checkpoints and saved trial contracts now record tokenization
  version 2 for the reviewed wrapper and include tokenizer implementation digests.
  Core restore accepts this explicit model wrapper, not bare experimental artifacts.
  Legacy version-1 word/byte bundles and datasets remain readable. Model input
  rejects uncovered text even when the experimental codec was configured to replace
  unknowns. Generated invalid UTF-8 bytes use an explicit preview-only replacement
  policy; reviewed training/evaluation inputs must remain lossless.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port 28842.
  Cancel created no version. Native selection rejected a 320-ID byte-BPE artifact
  and a 98-ID Unigram artifact with lossy heldouts before any model trial. Confirmed
  character-BPE selection created dataset f3dfa6aa363445d4b455ec3774364c28 with
  60 actual IDs (PAD 57 / BOS 58 / EOS 59), preserving original records/splits.
  Separate native training approval created trial 9b739bf134284b928af8eaf536324e90
  and completed 100 real Metal SGD steps from fresh weights; step-50 checkpoint and
  final bundle restored the exact dataset tokenizer hash and model vocabulary 60.
- Native pipeline inspection showed tokenization version 2. Backend/app restart
  reopened identical dataset/trial/pipeline records; native CPU preview generated
  12 tokens from the saved model for local prompt “orchard.” All 16 original files
  and all checkpoint/model artifacts remained unchanged across restart/preview.
  CPU/Metal maximum inference error was 2.5625318134103736e-07. Loss fell from
  4.1098761558532715 to 2.5369575023651123, but validation/test accuracies were
  0.42105263157894735 / 0.1: the 0.8 quality target failed and remains recorded as
  false. This verifies persistence/execution, not acceptable model quality or release.
- Evidence: /tmp/almg-tokenizer-adoption-native-qa/ contains selection/training
  consent, native rejection reports, adopted-dataset-ui.json, trial-ui.json,
  pipeline-ui.json, restarted-{dataset,trial,pipeline,preview}-ui.json,
  verification.json and native build/restart logs. Generated weights stay there.
- Verification: 436 Python tests passed with ALMG_METAL_TESTS=1, including actual
  adopted-Unigram Metal training; 34 Flutter tests passed and analysis/diff checks
  passed. Added tests cover all three codecs in model/checkpoint bundles, exact
  selection/provenance and source-permission preservation, separate approval,
  oversized/lossy rejection, atomic failure/concurrent changes, tampered policies/
  approvals/training provenance, version mismatch and explicit byte preview behavior.
- Remaining: larger/streamed tokenizer fitting is not implemented or verified; this
  bounded integration does not complete that scope. Existing dataset/hardware/
  Windows/scratch-space blockers stay open and were skipped without unchanged
  polling. No external collection, downloads, generated artifact commits or push;
  unrelated user edits and all existing training artifacts/weights are preserved.

P3-LMF-03 partial progress · reviewed fitting samples from streamed indexes · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed streamed indexes now offer “Fit tokenizer
  on streamed sample” and saved experiment inventory. Byte-BPE, character-BPE and
  Unigram use the existing configurable fitting engine; the native presets are
  caps 320/128/128 respectively. API configuration also supports existing explicit
  control-token definitions/unknown policies. Shared split comparison logic retains
  all existing small-dataset experiment formats and lossless/lossy accounting.
- A versioned pre-fit review selects at most 16 whole training records and 8 each
  validation/test, ordered by normalized group hash within the original saved
  splits. It excludes records over 4096 UTF-8 bytes without modifying/truncating
  them. Duplicate occurrence weights are not expanded. SQLite uses the existing
  bounded cache; selected text is at most 128 KiB. Fitting uses training samples
  only; held-out samples are comparison inputs only. This is explicitly a biased,
  bounded sample, not a complete/representative corpus fit or evaluation clearance.
- Exact sample metadata preserves normalized group, original first line/byte offset,
  raw-line hash, occurrences and byte size. Review/approval bind index revision,
  verified original source bytes, source permission snapshot, full configuration,
  training-text hash and implementation digests. Original/index signatures and
  hashes are rechecked; stale permission/source/scope changes reject publication.
  Missing source files return an actionable restore/verify error. Failed atomic
  publication removes temporary work without changing originals.
- Saved version-1 sample artifacts contain the codec, exact sample/provenance review,
  fitting-only approval and sample-scoped comparisons. Model training/release remain
  disabled, and the new namespace does not admit these samples into full streamed
  model training. Private ZIP export requires a separate review/confirmation and
  includes only manifest/codec, with explicit learned-phrase/permission-note warning.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port 28843.
  Opened the legacy fixed-byte tokenizer unchanged. Cancelled sample consent before
  fitting, then explicitly approved byte BPE on index
  ae5cb4ba27df462b9da27e64e3652bae (401 records; split populations 326/39/36).
  Exact sample counts were 16/8/8. Experiment 4f2d79f0db9b419d963852f83253b6ba
  fitted 320 IDs; all sampled records passed NFC round trips, with 702/715/728 tokens
  and sample byte/token ratios 6.9002849002849 / 3.4293706293706294 /
  3.258241758241758. These numbers do not describe the unsampled records.
- Backend/app restart reopened the exact saved manifest. A repeat native fit with
  final recovery handling created 493e22e5cba747eeab014a67d2e2fbe6 and produced the
  same tokenizer hash/comparisons. Native Save exported its private ZIP; standalone
  codec restore round-tripped unseen “café 世界 🚀” Unicode text. All six original
  source/index/legacy-tokenizer files stayed byte-identical; no model trial existed.
  Evidence: /tmp/almg-stream-tokenizer-sample-native-qa/ contains native consent,
  sample/reopened/final experiment JSON, legacy tokenizer JSON, export consent/save
  evidence, ZIP, verification.json, build/restart and verification logs.
- Verification: 442 Python tests passed with ALMG_METAL_TESTS=1; 34 Flutter tests
  passed, analysis/diff checks passed. Added tests cover training-only fitting against
  an independent codec fit, bounded whole-record selection/oversized exclusion,
  all three codecs/control policies, raw provenance, permissions/source invalidation,
  missing-source recovery, interrupted/concurrent publication, export/tamper/reload,
  no model authorization and preserved existing artifacts.
- Remaining: full-corpus streamed fitting, incremental/resumable learned-tokenizer
  fitting and full-population learned-tokenizer comparison/admission remain open.
  Larger-than-RAM and independent hardware/Windows/scratch-space blockers were not
  re-polled. No external collection, downloads, weight changes, generated artifact
  commits or push; unrelated user edits and prior artifacts are preserved.

P3-LMF-03 partial progress · resumable full-index learned-tokenizer comparison · 2026-11-20:
- [ ] P3-LMF-03 remains open. Saved streamed tokenizer experiments now offer a
  separately confirmed “Compare tokenizer across full index,” saved report inventory,
  pause and explicit resume. Every unique record in the original saved splits is
  visited without refitting the sampled codec or expanding duplicate occurrences.
  Production steps process at most 100 records or roughly 1 MiB of input, with at
  most one bounded indexed record beyond the byte threshold; SQLite retains its
  bounded cache and reports retain no source text.
- Version-1 reports bind experiment/tokenizer/index/source revisions and file
  signatures, source permissions, implementation/runtime and comparison-only
  approval. Start/final completion verify full index/source hashes; each batch checks
  source signatures, manifest/artifact integrity and scope before and after reading.
  Cursor and counters are published atomically together. Implementation/source/
  permission changes and storage failures preserve the last saved batch. Restarts
  do not automatically resume processing; complete records remain immutable.
- Full-population split results include character coverage, source occurrences,
  encoded/lossless/lossy/unsupported/failed records, total encoded tokens, explicit
  UNK/boundary overhead and lossless-only compression/efficiency. Records over
  4096 bytes are counted as unsupported without truncation. Coverage includes their
  characters; efficiency excludes unsupported/lossy records. Exact round-trip success
  requires all records in a completed split to encode losslessly. Bounded finding
  samples (20 per category) retain affected groups and original line/byte/hash
  provenance, while aggregate totals cover the full population. No contamination
  clearance, model-vocabulary compatibility or model training approval is implied.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port 28844.
  Cancel did not create a report. Confirmed Unigram comparison on the 413-record
  coverage fixture, paused at 80/413, restarted backend/app and reopened the exact
  saved record/revision. Explicit native resume completed report
  31e6947b5b254fde8c3f06341e9701ad. Split totals were 319/47/47; unsupported counts
  were 8/3/1 (12 total). One validation record required two UNKs and was reported
  lossy, never lossless. Full-record round-trip flags correctly remained false.
- A second native byte-BPE comparison, f35772e4c4324d0c8884de0e6efc043e, completed
  all 401 records of the existing clean fixture (326/39/36), with all-record lossless
  success true. This remains a sample-fitted 320-ID codec, not model admission.
  Independent per-record encoding matched both reports' split totals, token counts,
  lossless bytes and UNKs. All 16 original source/index/tokenizer files stayed
  byte-identical; no model trial or tokenizer refit occurred. QA used one-record
  batches to make native pause deterministic; production defaults stayed at 100.
- Evidence: /tmp/almg-full-tokenizer-comparison-native-qa/ contains consent,
  paused-comparison-ui.json, restarted-paused-comparison-ui.json,
  completed-comparison-ui.json, positive-full-comparison-ui.json,
  verification.json, original-file fingerprints and build/restart/test logs.
- Verification: 446 Python tests passed with ALMG_METAL_TESTS=1; 34 Flutter tests
  passed; analysis/diff checks passed. Added tests cover independent full-population
  accounting, both batch bounds, explicit no-refit assertion, oversized/OOV/UNK
  handling, restart/idempotence, code/source/permission changes, atomic save failure,
  mid-batch scope changes, preserved progress and report tampering.
- Remaining: full-corpus and incremental/resumable learned-tokenizer fitting, plus
  streamed model-input/admission integration, remain open. Full-index comparison
  does not turn sampled fitting into a full-corpus fit. Existing larger-than-RAM,
  hardware/Windows/scratch-space blockers were skipped without unchanged polling.
  No external collection, downloads, weight changes, generated artifact commits
  or push; unrelated user edits and existing training artifacts are preserved.

P3-LMF-03 partial progress · resumable whole-training-split one-merge byte BPE · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed indexes now offer a separately reviewed
  “Fit byte BPE on full training split,” saved fitting inventory, pause, explicit
  resume and private export. This initial whole-split baseline supports vocabulary
  caps 256/257 and learns at most one merge. It counts adjacent UTF-8 byte pairs in
  every unique training record, never heldouts or expanded duplicate occurrences,
  with minimum pair frequency two and lexicographic byte-ID tie breaking. It does
  not claim larger-vocabulary iterative BPE fitting.
- SQLite stores at most 256² distinct pair counters with the existing bounded cache.
  Per-record counters are bounded by the whole-record 65536-byte input limit. No
  whole-corpus token sequence is retained in memory or copied to work storage. Production batches stop at 100 records or roughly 1 MiB plus at most
  one bounded record. A 64 MiB scratch-space admission check protects counter storage.
  Counts, cursor, byte/record totals and an ordered training-group hash chain commit
  in the same transaction. Source/index signatures, hashes, permissions, code and
  runtime bind approval/resume; changed scope preserves prior progress.
- Publication uses an atomic artifacts-directory rename after committed counting.
  Interrupted publication resumes without recounting. A lost response after rename
  is recovered as the existing complete artifact, without overwriting it. The new
  versioned codec format explicitly stores its training-chain hash convention,
  actual count, cap and one-merge/64-KiB policies; it does not masquerade as the
  earlier canonical-training-array binding. Standalone reload/encode/decode and
  private manifest/codec ZIP export are supported. Pair databases and source text
  are excluded from export. This codec is not admitted to model training.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port 28845.
  Cancel created no fit. Explicit approval scanned the full 319-record training
  population of index 393aeda5b72d4e8dac42b0568c1f45f2 (413 total; 47 validation
  and 47 test records excluded). Native pause saved 120/319 records; backend/app
  restart reopened the exact saved record and required explicit resume. Fit
  51ba3a43ea88472884822929db0547cd completed 319 records / 57644 UTF-8 bytes,
  including all eight training records above 4096 bytes without truncation.
- The published codec has 257 IDs and learned [32,97] (space followed by “a”) at
  frequency 3911. Independent full-training-split pair counts, training bytes/count
  and the ordered group-chain hash matched exactly. Native Save exported a ZIP
  containing only manifest.json and tokenizer.json. Standalone restore round-tripped
  unseen Unicode and a long Unicode record. All 16 original source/index/tokenizer
  files stayed byte-identical; no model trial existed. QA used one-record batches
  for deterministic native pause; production remained at 100.
- Evidence: /tmp/almg-whole-split-bpe-native-qa/ contains native fitting consent,
  paused-fit-ui.json, restarted-paused-fit-ui.json, complete-fit-ui.json,
  export consent/save evidence, ZIP, verification.json, original fingerprints and
  build/restart/test logs. Generated work databases and codec artifacts stay there.
- Verification: 451 Python tests passed with ALMG_METAL_TESTS=1; 34 Flutter tests
  passed, analysis/diff checks passed. Added tests independently check global pair
  selection and heldout exclusion, exact whole-training hash/counts, long Unicode,
  restart/idempotence/export, invalid cap/confirmation/disk/code/permission gates,
  atomic counter+cursor rollback, publication interruption/lost-response recovery,
  explicit zero-merge baseline and tampered codecs. Existing formats remain intact.
- Remaining: iterative multiple-merge full-split BPE and full-split character-BPE/
  Unigram fitting, plus learned streamed-tokenizer model-input/admission integration,
  remain open. This one-merge baseline does not establish larger-than-RAM ingestion
  verification or resolve the existing hardware/Windows/scratch-space criteria;
  unchanged blockers were skipped. No external collection, downloads, weight
  changes, generated artifact commits or push; unrelated user edits are preserved.

P3-LMF-03 partial progress · resumable iterative full-training-split byte BPE · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed indexes now offer a separately reviewed
  iterative byte-BPE fit over the whole saved training population. The new versioned
  worker supports vocabulary caps 256–272 (up to 16 learned merges); the native
  preset fits four merges for cap 260. After every selected global pair it re-encodes
  original training records using the learned prefix and recounts pairs. Minimum
  frequency two, lexicographic token-ID ties and document boundaries match the
  existing bounded BPE fitter. Heldouts and duplicate occurrence weights are excluded.
- Each pass commits cursor, counters, population chain and learned-prefix transition
  atomically. The next pass starts with cleared counters and a reset cursor in the
  same transaction that saves its new merge. Every pass verifies the same full
  training-group chain and byte/count population. SQLite counters remain disk-backed;
  only bounded record/token buffers are used, without storing a whole-corpus token
  sequence. Input records remain whole up to 64 KiB; selected pieces retain the
  existing 4096-byte bound. Counting stops early when no pair reaches frequency two.
- The separate iterative namespace/codec format preserves existing one-merge job
  and artifact formats. Pending jobs require unchanged source/permissions/code;
  explicit pause/restart/resume and recoverable atomic publication are retained.
  Saved manifests include ordered merge IDs, pairs, frequencies, pass count and
  full-training binding. Private ZIP export includes only manifest and codec.
  Model training/release remain disabled; this is not generated-model admission.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port 28846.
  Reopened the earlier one-merge fit unchanged. Cancel created no iterative job.
  Explicit native fitting created 6fa1c7a3e0de4d80a7b336c74ddfe128 on the existing
  319-record training split (57644 UTF-8 bytes, including eight records over 4 KiB).
  Pause occurred during pass two at 115/319 records, after merge [32,97] was saved.
  Backend/app restart reopened the exact partial record/revision; explicit resume
  completed four passes and published 260 IDs.
- Learned pairs were [32,97], [98,99], [100,101], [102,103], each at frequency 3911.
  Independent full-training recoding/pair counts matched every rank, ID and frequency,
  and the full-training chain/byte count matched. Native Save exported a two-file
  private ZIP whose standalone codec round-tripped unseen and long Unicode text.
  All 19 original source/index/tokenizer/legacy-fit files remained byte-identical;
  no model trial existed. QA used one-record batches for deterministic cross-pass
  pause; production bounds remained 100 records/roughly 1 MiB per batch.
- Evidence: /tmp/almg-iterative-stream-bpe-native-qa/ contains legacy-one-merge-ui.json,
  iterative consent, paused-iterative-fit-ui.json, restarted-paused-iterative-fit-ui.json,
  complete-iterative-fit-ui.json, export consent/save evidence, ZIP, verification.json,
  original fingerprints and native build/restart/test logs.
- Verification: 456 Python tests passed with ALMG_METAL_TESTS=1; 34 Flutter tests
  passed; analysis/diff checks passed. New tests compare four- and sixteen-merge
  output with the existing fitter oracle, verify exact between-pass restart,
  atomic prefix/counter/cursor rollback, publication recovery, early no-pair stop,
  cap rejection, long Unicode round trips and continued legacy one-merge execution.
- Remaining: full-split vocabularies beyond this bounded 16-merge engine, full-split
  character-BPE/Unigram fitting and learned streamed-tokenizer comparison/model-input
  admission remain open. Larger-than-RAM ingestion and independent hardware/Windows/
  scratch-space criteria remain unverified and were skipped without unchanged
  polling. No external collection, downloads, weight changes, generated artifact
  commits or push; unrelated user edits and previous artifacts are preserved.

P3-LMF-03 partial progress · full-index comparison of completed whole-split BPE fits · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed one-merge and iterative whole-training-split
  BPE fits now offer separate full-index comparison and saved comparison inventory.
  Typed references bind the fitting namespace/ID/revision and exact codec hash;
  pending or mismatched fitting kinds reject before a report is created. The new
  report format/namespace leaves existing sample-tokenizer comparisons unchanged.
- Comparisons use the actual whole-split codecs' 65536-byte input limit rather than
  the sample experiment's 4096-byte limit. They visit every unique record in saved
  train/validation/test splits without refitting or expanding duplicate weights.
  Reports retain full-population coverage, lossless-only efficiency, unsupported/
  failure counts and bounded affected-record provenance without storing source text.
  Input/index/fitting-manifest/codec signatures and hashes are checked around bounded
  batches; code/runtime/permission changes preserve the last committed cursor/counts.
  Same-byte codec rewrites during a batch also invalidate its signatures.
- Native pause/restart/explicit resume use the existing comparison controls. Whole-
  split fits and sample-fitted tokenizers retain their distinct record limits and
  provenance; historical sample reports are not reinterpreted or rewritten. Positive
  round trips do not establish contamination clearance, generated-model vocabulary
  compatibility or training/release approval. Both remain explicitly disabled.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port 28847.
  Reopened legacy sample report 31e6947b5b254fde8c3f06341e9701ad unchanged with its
  original 4096-byte limit and 12 unsupported records. Cancel created no new report.
  Confirmed iterative-codec comparison dc802c1d20e14524a60b4093859c0b28, paused at
  90/413 records, restarted backend/app and reopened the exact saved record/revision.
  Explicit resume completed all 413 records (319/47/47 by split) losslessly, including
  all 12 records above 4096 bytes, with zero unsupported/failed/lossy records.
- A second native scan, 0e18609755264786b4ff470429eb1073, completed the same full
  index using the earlier one-merge codec and also round-tripped all records. Whole-
  split training token counts were 42000 for the four-merge codec and 53733 for the
  one-merge codec; independent per-record encoding matched both reports' split
  record/token/byte counts. Codec hashes remained exactly those of the original
  completed fits. All 24 original source/index/tokenizer/fitting/legacy-report files
  remained byte-identical; no fit was advanced and no model trial existed. QA used
  one-record batches for deterministic pause; production bounds stayed at 100.
- Evidence: /tmp/almg-fitted-bpe-comparison-native-qa/ contains legacy sample JSON,
  comparison consent, paused-fitted-comparison-ui.json,
  restarted-paused-fitted-comparison-ui.json, complete-iterative-comparison-ui.json,
  complete-one-merge-comparison-ui.json, verification.json, original fingerprints
  and native build/restart/test logs.
- Verification: 460 Python tests passed with ALMG_METAL_TESTS=1; 34 Flutter tests
  passed; analysis/diff checks passed. New coverage independently checks full-record
  encoding over 4 KiB for both completed codec kinds, no refitting/advancing fits,
  typed/completed/review/permission gates, restart/idempotence, atomic-save failure,
  codec/source tampering and same-byte mid-batch signature changes with saved
  progress preserved. Existing sample comparisons and one-merge formats remain intact.
- Remaining: larger-vocabulary full-split fitting, full-split character-BPE/Unigram
  fitting and learned streamed-tokenizer model-input/admission integration remain
  open. Larger-than-RAM ingestion and independent hardware/Windows/scratch-space
  criteria stay unverified and were skipped without unchanged polling. No external
  collection, downloads, weight changes, generated artifact commits or push;
  unrelated user edits and all existing artifacts are preserved.

P3-LMF-03 partial progress · wider decoder profile and trained byte-BPE persistence · 2026-11-20:
- [ ] P3-LMF-03 remains open. The registered bounded decoder now validates 4–512
  vocabulary IDs and advertises its architecture profiles. Models through 256 IDs
  retain architecture component version 1; larger vocabularies select version 2.
  Matrix serialization stays in the existing parameterized decoder format, with
  strict stage/config/pipeline binding in bundles and checkpoints. Legacy word/byte
  and reviewed-tokenizer models remain readable without rewriting their artifacts.
- Reviewed model-tokenizer wrappers, compatibility and immutable dataset adoption
  now use the same 512-ID limit, including reserved controls. Compatibility reports
  explicitly use version 2 and record the selected architecture profile; native
  controls offer exact actual IDs or the 512-ID maximum. Bare experiment artifacts
  remain ineligible for direct pretraining. Lossy/OOV inputs, mismatched dimensions
  and stale reviews still reject. Selection does not grant model-training approval.
- Wider-profile generated previews have a separately stored policy: at most 160
  IDs (128 context plus 32 generated) and 65536 UTF-8 output bytes, with explicit
  byte replacement, control skipping and visible UNK. Dataset encoding/round trips
  retain their strict input limits and no unknown replacement. This prevents large
  learned byte pieces from being incorrectly constrained by the dataset's 4-KiB
  decode limit during private generation; invalid IDs and output overflow still fail.
- Local app verification: rebuilt native macOS ALMG on isolated fixture port 28848.
  Opened the existing 60-ID trial unchanged. Native lossy-Unigram selection still
  rejected; 16-vs-320 model vocabulary review still reported mismatch. Exact 320-ID
  byte-BPE review passed under architecture profile 2. Confirmed selection created
  immutable dataset 516417a89b1044b7b03f66278daadae1; separate native trial approval
  created b27fccaba5dc4ccb90cf515084aba230 and completed 100 real fresh-weight Metal
  SGD steps with 5760 trainable parameters.
- Native pipeline inspection and independent reload verified architecture version 2,
  tokenization version 2, model vocabulary 320 and the exact saved tokenizer in the
  step-50 checkpoint/final bundle. CPU/Metal maximum inference error was
  7.692969763439805e-07. Loss fell from 5.7667012214660645 to 0.9861118793487549,
  but validation/test accuracy was 0/0: the 0.8 quality target failed and remains
  recorded false. This verifies execution/persistence, not model quality or release.
- Backend/app restart reopened identical dataset/trial/pipeline records. Native CPU
  preview generated 12 tokens for “banana” using the saved wider model. All 27
  original source/dataset/experiment/legacy-model files and all new checkpoint/model
  artifacts stayed byte-identical across restart/preview. The legacy 60-ID bundle
  still restored as architecture version 1. No public release was approved.
- Evidence: /tmp/almg-wide-byte-bpe-native-qa/ contains legacy-trial-ui.json, lossy
  rejection, mismatch/wide compatibility reports, selection/training consent,
  wide-{dataset,trial,pipeline}-ui.json, restarted-wide-{dataset,trial,pipeline,preview}
  evidence, verification.json, original fingerprints and native build/restart/test logs.
- Verification: 465 Python tests passed with ALMG_METAL_TESTS=1; 34 Flutter tests
  passed; analysis/diff checks passed. New tests verify 512-ID fresh initialization
  without student file access, causality, maximum-size model persistence within the
  existing loader bound, architecture/profile tampering, 320-ID model/checkpoint
  and actual Metal execution, legacy loading, strict vs generated decoding, byte
  controls/UTF-8 continuity, replacement-output expansion and explicit preview bounds.
- Remaining: full-split character-BPE/Unigram and larger-vocabulary fitting, plus
  learned streamed-tokenizer model-input/admission integration, remain open. The
  widened profile alone does not approve streamed training. Larger-than-RAM and
  independent hardware/Windows/scratch-space criteria remain unverified and were
  skipped without unchanged polling. No external collection, downloads, generated
  artifact commits or push; user edits and prior weights/artifacts are preserved.

P3-LMF-03 partial progress · learned-tokenizer streamed windows and masked input inspection · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed full-split one-merge and iterative byte-BPE
  comparisons now offer separately confirmed learned-tokenizer window preparation.
  Admission requires an exact completed lossless full-index comparison, matching
  exhaustive five-word-shingle overlap evidence with zero cross-split findings,
  unchanged source/codec/permission bindings and nonempty saved splits. Lexical
  evidence does not establish absence of short or semantic contamination.
- The separate v1 learned-window namespace stores at most 17 IDs per window with
  stride 16, preserving document boundaries, unique-record split assignments,
  original line/byte/hash references and occurrence counts without expanding
  duplicates. Each batch transaction commits its windows, source references,
  cursor and counters together; interrupted publication resumes without recounting.
  Records encoding to fewer than two tokens fail explicitly rather than disappearing.
  Preparation streams at most 100 records/about 1 MiB of source characters per step;
  supported records retain the full-split codec's 64 KiB UTF-8 limit.
- Native read-only batch inspection pages 1–16 windows with reviewed learned-ID
  bounds, shifted targets, width-16 storage padding and mandatory loss masks.
  The codec hash and vocabulary size accompany each batch. This path grants no
  model-training approval and exposes no fixed-byte optimizer or approach-planning
  action. Existing fixed-byte windows and their controls retain their prior route.
- Local app evidence: rebuilt and launched the macOS app against isolated local
  fixtures on port 28849. A 35-record lossless comparison with 156 cross-split
  findings was rejected before window creation. Cancelling clean-source consent
  also created nothing. Confirmed preparation 7d0b7868954f4d35b5095b57a0a43a6f
  paused at 85/401 records; restarting both backend and app restored the exact
  saved record, and explicit native resume completed all 401 records with 260 IDs.
  Observed 4,714 train / 569 validation / 522 test windows and 89,228 targets.
  The native inspector displayed train/validation/test arrays, pagination, learned
  IDs through 259 and a padded test batch with lengths [16,16,4,16], totaling
  52 unmasked targets. No optimizer controls or model trials were created.
- Independent verification compared all 5,805 saved windows with fresh source
  encodings, verified shifted targets/masks/source references in captured native
  batches and confirmed all 20 pre-existing source/fit/comparison/overlap fixture
  files remained byte-identical. Evidence stays outside Git at
  /tmp/almg-learned-window-native-qa/verification.json and *-ui.json/*-ui.txt.
  Regression validation: 471 Python tests with Metal checks and warnings treated
  as errors, 35 Flutter tests, clean Flutter analysis and successful macOS rebuild.
  Focused tests cover both fit kinds, incomplete comparisons, consent/stale review,
  contamination, exact restart/cursors/splits/provenance, single-token rejection,
  transaction rollback, publication recovery and mid-batch/permission changes.
- Remaining: learned streamed optimizer/training admission and checkpoint recovery,
  larger full-split vocabulary budgets, full-split character-BPE/Unigram fitting
  and broader acceptance verification. P3-LMF-01 is already complete. Unchanged
  larger-than-RAM, physical power and Windows verification blockers stay open and
  skipped. No external collection, downloads, generated artifacts or weights are
  included in this change; no push is authorized or performed.

P3-LMF-03 partial progress · learned-vocabulary masked optimizer diagnostic · 2026-11-20:
- [ ] P3-LMF-03 remains open. The learned-window batch inspector now offers a
  separately confirmed five-step Metal diagnostic using the exact saved learned
  vocabulary (4–512 IDs supported by the registered architecture). Reviewed codec,
  window revision, source/permission/contamination bindings and the inspected
  training batch must match before initialization and again after GPU execution.
  Student parameters start from new weights; pretrained weights are never loaded.
- A bounded learned-tokenizer split iterator performs full integrity checks at
  split boundaries and file/permission guards around each page, retaining at most
  16 windows per batch. Consumers must exhaust the iterator before publishing
  metrics. Evaluation covers every saved validation/test window with zero held-out
  optimizer updates and aggregates masked loss/correct counts by real targets.
  Changed sources, incomplete populations or invalid metrics prevent publication.
- The shared numerical implementation retains the legacy fixed-byte route/report
  format. Learned diagnostics use their own report namespace/version and record
  codec hash, actual vocabulary, architecture profile, inspected-batch digest and
  provenance, all parameter tensor updates, padding loss/gradient errors and CPU
  inference agreement. Model weights are discarded; only diagnostic JSON is saved.
  Numerical success does not approve training, establish usable quality or release.
- Local native verification: rebuilt and launched the macOS app on port 28850
  using the previously completed 401-record learned-window fixture. Inspected a
  training batch with learned IDs above 255 and lengths [16,16,4,16]. Cancelling
  consent created no report. Confirmed five-step check
  a54984a70f0e4798a232eddc32a3a53b used 260 IDs/architecture version 2, updated all
  parameter tensors and reduced batch loss 5.591536521911621 → 5.449448585510254.
  Twelve padding positions produced masked target loss error 0 and gradient error
  7.450580596923828e-09; CPU/Metal inference error was 3.5565019707028966e-08.
- The app reported full validation coverage: 569 windows / 8,732 targets in 36
  batches; full test coverage: 522 windows / 8,028 targets in 33 batches. Neither
  held-out split received optimizer updates. Validation/test next-token accuracy
  was approximately 0.191/0.192; no quality or release claim follows from this
  five-step diagnostic. Restarting backend and app reopened the exact report from
  Saved optimizer checks. Independent database counts, target totals and inspected
  batch hash matched; all 22 pre-existing source/fit/comparison/window files stayed
  byte-identical. Only one new diagnostic JSON appeared; no model/trial was saved.
- Verification: 477 Python tests passed with ALMG_METAL_TESTS=1 and warnings as
  errors, 36 Flutter tests passed, analysis/diff checks were clean, and native
  build/restart succeeded. Added coverage includes actual wider Metal updates,
  padding invariance, CPU agreement, confirmation/stale scope, complete split
  traversal and target weighting, boundary validation frequency, permission/window
  rewrites between pages, post-GPU changes, report reload/separate namespaces and
  learned UI confirmation/history routing. Evidence remains outside Git in
  /tmp/almg-learned-optimizer-native-qa/verification.json, *-ui.json/*-ui.txt and logs.
- Remaining: approved durable streamed training, checkpoint recovery and model
  persistence for full-split learned codecs, larger full-split vocabulary budgets,
  full-split character-BPE/Unigram and broader acceptance verification. Unchanged
  hardware/Windows/larger-than-RAM blockers stay open and skipped. No external
  collection, downloads, generated artifacts/weights in Git or push occurred.

P3-LMF-03 partial progress · versioned full-split byte-BPE budgets through 512 IDs · 2026-11-20:
- [ ] P3-LMF-03 remains open. Whole-training-split iterative byte BPE now accepts
  reviewed vocabulary caps from 256 to 512. Native fitting offers 260 (existing
  default), 256, 272, 320 and 512-ID budgets, explaining the complete-split pass
  cost and early stop when no pair occurs twice. Consent displays the selected
  cap and merge count; changing the approved budget invalidates its review.
- Caps above 272 use separate v2 fitting/review/codec contracts with at most 256
  learned merges. Caps through 272 retain the v1 contract and sixteen-merge policy;
  legacy codec artifacts round-trip without rewriting. Schema/budget relabeling
  is rejected. The 64 KiB record limit, 4 KiB piece limit, unique-training-only
  population, frequency-2/lexicographic merge rule, disk-backed counters and
  transactional batch/pass recovery remain enforced. Training/release stay disabled.
- Native fit inventory, explicit resume, full-index comparison and private export
  recognize both versions. Local app verification rebuilt/launched macOS on port
  28851, reopened the unchanged legacy 260-ID fit, selected 512-ID consent and
  cancelled without creating a fit, then completed 320-ID fit
  bafdac8a01b14bed83b0461ed6c37544 with 64 merges/passes over 30 training records.
- Maximum-budget fit 15989af1852a44ddb1a0e020ffc83f62 paused after six completed
  passes at 24/30 records in its current pass. Restarting backend and app restored
  the exact saved record, selected 512-ID cap and cursor; explicit native resume
  completed all 256 passes/merges with 512 actual IDs. A second backend/app
  restart reopened the identical completed v2 record and unchanged artifact files.
- Native full-index comparison 7ac41036f95c460c8244436c538dcef2 round-tripped all
  40 records losslessly (30 train, 7 validation, 3 test) without refitting. This
  lossless check does not clear contamination or approve pretraining. Native export
  saved a private ZIP in the isolated QA directory; independent inspection found
  exactly tokenizer.json and manifest.json matching the saved v2 codec/report.
- Independent verification reconstructed every one of the 256 merge choices and
  frequencies from the complete training-only population, verified its ordered
  group chain, confirmed the 320-ID fit matches the first 64 choices and checked
  encode/decode on every split. All 27 pre-existing source/index/fit/comparison/
  window/diagnostic fixture files stayed byte-identical. Evidence remains outside
  Git in /tmp/almg-stream-bpe-budget-native-qa/verification.json, native *-ui.json/
  *-ui.txt, private ZIP, fingerprints and build/restart/test logs.
- Validation: 479 Python tests with Metal checks and warnings as errors, 36 Flutter
  tests, clean Flutter analysis/diff checks and successful native rebuilds. Added
  cases compare actual 320/512-ID fits to the deterministic BPE oracle, resume
  after seventeen passes, validate maximum-budget export/reload and multilingual/
  long-record round trips, reject invalid caps and changed review/version labels,
  preserve v1 codec bytes and verify early stopping below the requested budget.
- Remaining: full-split character-BPE/Unigram, approved durable streamed training
  and checkpoint/model persistence for full-split codecs, and broader acceptance.
  Budgets beyond 512 remain outside the supported model/codec profile. Independent
  physical/Windows/larger-than-RAM blockers remain open and skipped without polling.
  No external collection, downloads, generated artifacts/weights in Git or push.

P3-LMF-03 partial progress · resumable full-training-split character BPE · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed streamed indexes now offer separately
  reviewed full-training-split character BPE with vocabulary caps 32–512 (native
  choices 128 default, 32, 64, 256, 512). A first disk-backed pass counts the entire
  unique training-record NFC alphabet; it freezes sorted character IDs before
  counting any merge pairs. Held-out records and duplicate occurrence weights do
  not contribute. An alphabet exceeding the approved cap rejects that batch
  without publishing or losing earlier committed progress; a larger cap needs a
  new exact review. This does not approve model training or release.
- The separate v1 fitter/codec namespace supports whole records up to 64 KiB,
  pieces up to 4 KiB and up to 511 merges within the selected cap. Global pairs
  use minimum frequency two and lexicographic token-ID ties. Bounded source batches
  (100 records/about 1 MiB by default), alphabet/pair counters, cursor and pass
  transitions commit atomically in SQLite. Ordered training group-chain/byte totals,
  original source/index signatures, permission review and implementation binding
  are checked across alphabet discovery, merge passes and publication. Explicit
  resume handles interrupted discovery, counting and publication without refitting
  from held-outs. Early pair exhaustion may yield fewer IDs than requested.
- Full-index comparison now accepts this completed codec as a distinct
  character_bpe kind, retaining explicit uncovered-character counts and encoding
  failures instead of unknown substitution or alphabet expansion. Saved comparison
  and private codec/manifest export preserve source bindings. Existing byte-BPE
  kinds and completed artifacts remain readable. Streamed character model-window,
  optimizer and training admission stay unavailable in both UI and backend.
- Native verification: rebuilt/launched macOS on port 28852, reopened the existing
  512-ID byte-BPE fit, observed a 32-ID character alphabet rejection with no
  artifact publication, and cancelled 64-ID consent without creating another fit.
  Character fit 3293d6da28424a78b35bba018cbf872e paused in alphabet discovery at
  3/31 training records. Restarting backend and app restored the exact record;
  native resume froze 40 characters and completed 24 merges for 64 actual IDs,
  using all 31 unique training records / 25,763 UTF-8 bytes including a >4 KiB record.
  QA-only one-record steps/response latency made the discovery pause deterministic;
  production batching is unchanged.
- Native comparison 0c063256e41144fd93ad7d15c9223451 scanned all 42 records:
  train 31/31, validation 7/8, test 3/3 lossless, zero unsupported records. The
  held-out-only Ω remained outside the alphabet and produced exactly one uncovered
  character/encoding failure; all_records_lossless stayed false. Coverage comparison
  does not clear contamination or establish model quality. Native private ZIP
  export contained exactly the matching codec and provenance manifest. A second
  backend/app restart reopened the identical completed record/artifacts.
- Independent verification reconstructed the complete training-only alphabet,
  every count and all 24 merge ranks/frequencies, verified the ordered group chain,
  multilingual/long-record round trips and strict held-out rejection. All 38 prior
  source/index/byte-fit/comparison/window/diagnostic fixture files stayed byte-identical.
  Evidence remains outside Git at /tmp/almg-stream-character-bpe-native-qa/verification.json,
  *-ui.json/*-ui.txt, private ZIP, fingerprints and build/restart/test logs.
- Validation: 484 Python tests with Metal checks and warnings as errors, 36 Flutter
  tests, clean Flutter analysis/diff checks and successful native rebuilds. Added
  cases cover discovery and merge-phase recovery, complete alphabet counts, a rare
  training-only character, independent global pair choices, duplicate handling,
  >4 KiB Unicode round trips, held-out coverage failures, vocabulary/review guards,
  alphabet and pair transaction rollback, publication recovery, permission changes,
  export and blocked character-window admission.
- Remaining: full-split Unigram, streamed character-codec model admission and
  durable approved streamed training/checkpoint/model persistence, plus broader
  acceptance. Independent physical/Windows/larger-than-RAM blockers remain open
  and skipped without polling. No external collection, downloads, generated
  artifacts/weights in Git or push; unrelated edits and prior artifacts preserved.

P3-LMF-03 partial progress · reviewed full-split character model inputs and numerical checks · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed full-split character-BPE comparisons now
  offer reviewed model-input preparation only when every saved record round-trips
  losslessly, all splits are nonempty, and a matching exhaustive lexical overlap
  report has zero cross-split findings. Source/index/codec/permission revisions
  remain bound to the exact review. The actual codec vocabulary must match its
  saved manifest and fit the registered decoder's 4–512-ID profile before any
  windows are created. Lexical evidence does not establish semantic cleanliness.
- Character inputs use v2 window, masked-batch and numerical-diagnostic contracts
  with an explicit character model-input profile (vocabulary, architecture version,
  context 16, no special tokens, no training/release approval). Existing byte-BPE
  v1 contracts and completed artifacts remain readable without rewriting. Windows
  preserve document boundaries, original split/group/line/byte/hash provenance,
  stride-16 next-token targets, duplicate counts without expansion and exact
  padding masks. Records shorter than two encoded tokens reject explicitly.
- The separately confirmed five-step Metal diagnostic accepts only the matching
  v2 character batch/profile, starts new weights, checks all parameter tensors,
  CPU inference and masked loss/gradient invariance, and evaluates every saved
  validation/test window without held-out updates. The character padding probe
  uses a guaranteed different valid ID and records how many masked targets changed;
  a 127-ID regression test prevents a vacuous unchanged-target probe. Weights are
  discarded and only the numerical report is persisted. Durable training, model
  persistence, quality acceptance and release are not approved by this path.
- Native verification rebuilt/launched macOS on port 28853, reopened legacy v1
  byte inputs, rejected a character comparison with a held-out-only coverage gap
  before creating windows, and cancelled clean-source consent without creating work.
  Character preparation 4f852a8cb89a45ce9cb31f0bc5f44607 paused at 7/401 records;
  restarting backend/app restored the identical record. Explicit native resume
  produced 1,486 train / 187 validation / 174 test windows and 28,428 real targets
  with 64 IDs/architecture version 1. All three split inspectors and pagination
  were exercised, including padded training arrays. QA-only one-record steps and
  response latency made the pause deterministic; production batching is unchanged.
- Cancelling diagnostic consent saved nothing. Final native check
  0f6df76a6bd14940a27cfb9c0759739f changed its one padded target and reduced batch
  loss 4.16221809387207 → 4.023611545562744. Masked loss error was 0, gradient error
  1.4901161193847656e-08 and CPU/Metal error 3.355084141065667e-08. Evaluation
  covered all 187 validation windows / 2,921 targets in 12 batches and all 174 test
  windows / 2,713 targets in 11 batches, with zero held-out optimizer updates.
  Accuracy was about 0.042/0.036; this numerical test establishes no quality target.
  Completed windows and the exact final report reopened after further backend/app
  restarts. The earlier local diagnostic report was preserved as well.
- Independent checks compared all 1,847 windows and captured native arrays/masks/
  provenance with fresh source encodings, verified batch/report hashes and complete
  held-out counts, and confirmed all 49 prior source/fit/comparison/window/diagnostic
  files stayed byte-identical. No model/trial was saved. Evidence remains outside
  Git at /tmp/almg-character-input-native-qa/verification.json, *-ui.json/*-ui.txt,
  fingerprints and native build/restart/test logs.
- Validation: 489 Python tests with Metal checks and warnings as errors, 37 Flutter
  tests, clean Flutter analysis/diff checks and successful native rebuilds. New
  coverage includes v2 exact IDs/masks/provenance, complete split traversal, current
  profile/review/vocabulary/contamination guards, transaction rollback/publication
  recovery, actual character Metal updates, report reload, 127-ID padding changes
  and native UI routing. The prior held-out-character guard now explicitly requires
  a lossless comparison rather than rejecting the entire character family.
- Remaining: full-split Unigram, durable approved streamed training/checkpoint/model
  persistence for full-split codecs and broader acceptance. Independent physical,
  Windows and larger-than-RAM blockers remain open and skipped. No external
  collection, downloads, generated artifacts/weights in Git or push; unrelated
  user edits and prior artifacts are preserved.

P3-LMF-03 partial progress · resumable full-training-split Unigram candidate initialization · 2026-11-20:
- [ ] P3-LMF-03 remains open. Streamed indexes now offer separately reviewed
  full-split Unigram candidate preparation with a 32–512-ID budget. This delivers
  the fixed-candidate initialization stage only: no EM update, trained tokenizer,
  model-input admission or training/release approval is produced. Native inventory
  and consent text distinguish frequency-based initial probabilities from fitted
  model probabilities; candidate pieces may encode private text.
- The versioned candidate inventory counts every unique training record, excluding
  held-out records and duplicate occurrence weights. NFC characters include the
  complete training alphabet; within-word substrings of length 2–8 accumulate in
  SQLite. Candidates occurring at least twice rank by frequency × (length − 1),
  then lexical order, matching the bounded Unigram selection rule. Alphabet IDs
  remain sorted first; selected substrings follow in sorted order. Positive initial
  probabilities normalize selected counts. No cross-word/document pieces or
  held-out alphabet expansion are introduced; alphabet overflow requires a new
  review with a larger cap and preserves prior committed progress.
- Per-step source buffers remain bounded to 100 records/about 1 MiB by default,
  each record to 64 KiB, and in-memory substring deltas to 4,096 entries before
  flushing into disk counters. Counts, training bytes, ordered group-chain hash and
  cursor commit together. Original source/index signatures, permission review,
  implementation binding and population checks guard publication. Interrupted
  batches roll back; interrupted publication resumes from sealed counts. Completed
  manifest/counter hashes and reconstructed initializers are checked on reload.
- Native verification rebuilt/launched macOS on port 28854, rejected a 32-ID budget
  whose training alphabet did not fit without publishing, and cancelled clean
  64-ID consent without creating another inventory. Candidate inventory
  d0739055d77743f6a76077bab5fcf381 paused at 8/326 training records. Restarting
  backend/app restored the exact saved record; explicit native resume completed
  all 326 unique training records, a 20-character alphabet, 12,897 distinct
  training substrings and 64 candidate IDs (20 characters plus 44 substrings).
  QA-only one-record steps/response latency made pause deterministic; production
  batching is unchanged. A second backend/app restart reopened the identical
  completed inventory with em_updates=0 and tokenizer_trained=false.
- Independent verification reconstructed all alphabet/substring counts, rankings,
  selected IDs, initial probabilities and the ordered training group chain. Initial
  probability mass summed to one. All 53 prior source/index/tokenizer/comparison/
  window/diagnostic fixture files stayed byte-identical; no model or trial was saved.
  Evidence remains outside Git at /tmp/almg-unigram-candidates-native-qa/verification.json,
  *-ui.json/*-ui.txt, fingerprints and native build/restart/test logs.
- Validation: 494 Python tests with Metal checks and warnings as errors, 37 Flutter
  tests, clean Flutter analysis/diff checks and successful native builds. Added
  cases cover >16-document full-population counting, bounded counter flushing,
  held-out-only character exclusion, >4 KiB records, no cross-word pieces,
  deterministic ranking/mass, cap/consent/review guards, transactional rollback,
  publication recovery, permission changes and mid-batch same-byte source rewrites.
  Candidate inventories are rejected as trained full-split comparison codecs.
- Remaining: resumable full-split Unigram EM fitting, likelihood checks and trained
  codec persistence/comparison/admission; durable approved streamed model training
  and checkpoint/model persistence; broader acceptance. Independent physical,
  Windows and larger-than-RAM blockers remain open and skipped. No external
  collection, downloads, generated artifacts/weights in Git or push; unrelated
  edits and prior artifacts are preserved.

P3-LMF-03 partial progress · resumable full-training-split Unigram EM and trained codec · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed candidate inventories now offer separately
  confirmed five-update full-split Unigram EM. The fixed training-only alphabet,
  piece IDs and initializer hash are preserved without pruning, sampling, held-out
  fitting or alphabet expansion. Six complete expectation/likelihood passes verify
  initial probabilities and each of five updates, using smoothing 1e-12 and strict
  finite/count/mass checks. A likelihood decrease beyond 1e-6 prevents publication.
  This trains a tokenizer only; student-model training and release stay disabled.
- The separate v1 fitter saves current probabilities, bounded expected-count
  vectors, likelihood, cursor, pass bytes/group chain and update history together
  in SQLite transactions. Batches process at most 100 records/about 1 MiB by default;
  forward/backward buffers belong to one record up to 64 KiB rather than the full
  corpus. Each pass must reproduce the frozen candidate training population and
  byte/group-chain totals. Candidate/source/index/permission signatures and code
  binding are rechecked before and after batches and at publication. Interrupted
  transactions preserve earlier progress; publication resumes from sealed state.
- Completed artifacts wrap the strict Unigram codec with full-split training and
  initializer bindings, five verified updates, six monotonic likelihood values,
  positive normalized probabilities, whole-record Viterbi encoding/decoding and
  strict uncovered-character rejection. Native saved fits, full-index comparison
  (distinct unigram kind) and private codec/manifest ZIP export are integrated.
  Candidate inventories remain explicitly untrained. Unigram model-window,
  optimizer and student-training admission remain unavailable in both UI/backend.
- Native verification rebuilt/launched macOS on port 28855 and cancelled EM consent
  without creating a fit. Fit d1bf650b04f040dfa535517c453f02ff paused with partial
  expected counts and likelihood at 9/326 records in its first pass. Restarting
  backend/app restored the exact saved record. Explicit native resume completed
  all six passes and five updates over the same 326 unique training records,
  retaining 64 pieces. QA-only one-record steps/response latency made pause
  deterministic; production batching is unchanged.
- Observed checked training log-likelihood history was
  [-164388.1851618082, -104835.31180334378, -102469.32388814804,
   -102431.1749368286, -102426.53942110574, -102425.64839593705]. Native comparison
  534f95ccb54440d0a3160034497f4d80 round-tripped all 401 records losslessly without
  refitting (326 train, 39 validation, 36 test). Lossless tokenization does not
  clear contamination or establish student-model quality. Native private export
  contained exactly matching tokenizer.json and manifest.json. A second backend/
  app restart reopened the identical completed codec, probabilities and history.
- Independent full-training EM recomputation matched every saved probability
  within 1e-12 and every likelihood within 1e-6, with exact frozen piece IDs/group
  chain and per-split encoded-token totals. All 56 prior source/index/candidate/
  tokenizer/comparison/window/diagnostic fixture files stayed byte-identical. No
  student model or trial was saved. Evidence remains outside Git at
  /tmp/almg-stream-unigram-native-qa/verification.json, *-ui.json/*-ui.txt, private
  ZIP, fingerprints and native build/restart/test logs.
- Validation: 498 Python tests with Metal checks and warnings as errors, 37 Flutter
  tests, clean Flutter analysis/diff checks and successful native builds. New tests
  compare all updates with the existing Unigram oracle, recover partial expectations,
  verify whole-record Unicode round trips/export/comparison, reject likelihood
  decreases/nonfinite statistics, guard consent/reviews/permissions/source rewrites,
  recover transaction/publication failure and keep model-input admission blocked.
- Remaining: full-split Unigram model-input/optimizer admission, durable approved
  streamed student training/checkpoint/model persistence and broader acceptance.
  Vocabulary pruning and subword sampling remain unsupported by the documented
  fixed-candidate Unigram implementation. Independent physical/Windows/larger-than-
  RAM blockers stay open and skipped. No external collection, downloads, generated
  artifacts/weights in Git or push; unrelated edits and prior artifacts preserved.

P3-LMF-03 partial progress · reviewed full-split Unigram model inputs and numerical checks · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed full-split Unigram codecs now qualify for
  model-input preparation only after an exact lossless comparison of every saved
  record, nonempty saved splits, matching exhaustive zero-cross-split lexical
  overlap evidence and a supported actual vocabulary of 4–512 IDs. Frozen trained
  probabilities, candidate/source/index/permission revisions and codec hashes stay
  bound to the review. Coverage gaps or changed probability files block admission;
  lexical evidence does not establish absence of short or semantic contamination.
- Unigram inputs use v3 window, masked-batch and numerical-report contracts with
  an explicit Unigram model-input profile. Existing byte v1 and character v2
  contracts remain readable unchanged. Viterbi IDs preserve document boundaries,
  split/group/line/byte/hash provenance, stride-16 targets and mandatory padding
  masks; duplicate occurrences are not expanded. Every record must encode to at
  least two valid IDs. Transactions and interrupted publication retain recoverable
  counters/cursors. Profile scope grants no student-training or release approval.
- The separately confirmed five-step diagnostic validates the exact v3 family,
  batch and vocabulary before fresh decoder initialization. It checks every
  parameter tensor, masked loss/gradient invariance with actually changed padded
  targets, CPU inference agreement and complete token-weighted held-out evaluation.
  No held-out optimizer updates occur. Model weights are discarded; only the
  versioned diagnostic report persists. Older diagnostic schemas remain readable.
- Native verification rebuilt/launched macOS on port 28856, reopened legacy v2
  character batches, rejected a Unigram comparison with a held-out coverage gap
  without creating windows, and cancelled clean-source consent without creating
  work. Unigram preparation d6db3bbb64114d4fb7dda6fc80e58242 paused at 9/401 records.
  Restarting backend/app restored the exact saved state; native resume completed
  2,432 train / 298 validation / 273 test windows with 44,637 targets and 64 IDs /
  architecture version 1. All split inspectors and pagination were exercised.
  QA-only one-record steps/response latency made pause deterministic; production
  batching is unchanged. Completed preparation reopened unchanged after restart.
- Cancelling diagnostic consent saved nothing. Native diagnostic
  85d8d88c818d4380bda9bb03a2aeccce changed all four padded targets and reduced batch
  loss 4.158256530761719 → 3.988203525543213. Masked loss error was 0, gradient
  error 1.4901161193847656e-08 and CPU/Metal error 3.9151893727051856e-08.
  Evaluation covered all 298 validation windows / 4,404 targets in 19 batches and
  all 273 test windows / 4,055 targets in 18 batches, with zero held-out updates.
  Accuracy was approximately 0.136/0.146; numerical success establishes no model
  quality or release target. A further backend/app restart reopened the exact
  saved v3 report through the native diagnostic inventory.
- Independent checks verified all 3,003 windows against fresh frozen-codec Viterbi
  encodings, captured native arrays/masks/source references, exact batch/report
  hashes, and all held-out populations/target totals. All 66 prior source/index/
  candidate/tokenizer/comparison/window/diagnostic files stayed byte-identical.
  No student model/trial was saved. Evidence remains outside Git at
  /tmp/almg-unigram-input-native-qa/verification.json, *-ui.json/*-ui.txt, fingerprints
  and native build/restart/test logs.
- Validation: 501 Python tests with Metal checks and warnings as errors, 38 Flutter
  tests, clean Flutter analysis/diff checks and successful native builds. New
  cases cover exact v3 arrays/provenance, full split traversal, current probability
  signatures, contamination rejection, publication recovery, actual source-bound
  Unigram Metal execution and report reload. UI tests retain the distinct v3
  family/review and explicitly label its diagnostic-only scope.
- Remaining: durable approved streamed student training, checkpoint recovery and
  model/tokenizer persistence for full-split codecs, plus broader acceptance.
  Fixed-candidate Unigram pruning/sampling remain unsupported. Independent physical,
  Windows and larger-than-RAM blockers stay open and skipped. No external collection,
  downloads, generated artifacts/weights in Git or push; unrelated edits and prior
  artifacts are preserved.

P3-LMF-03 partial progress · reviewed streamed-codec model bundle persistence contract · 2026-11-20:
- [ ] P3-LMF-03 remains open. Learned stream batch inspectors now offer a separate
  private model/tokenizer persistence check. It saves the tiny seed-7 decoder and
  exact reviewed full-split codec together, reloads them, compares every parameter
  tensor and CPU output, and verifies lossless source-record IDs. Consent states
  that saved model weights are untrained: zero optimizer updates, no student-training
  approval, no quality target and no release. Read-only source/codec/permission and
  inspected-batch bindings are rechecked before and after the operation.
- The new streamed model-tokenizer wrapper restores supported one-merge/iterative
  byte BPE, character BPE and trained Unigram codecs without refitting. It binds
  window, fit, index, original source, codec and persistence-approval revisions,
  validates 4–512 actual IDs, preserves strict lossless input encoding and caps
  preview decoding at 160 IDs / 64 KiB (explicit byte replacement only for preview).
  Bounded-dataset refitting is rejected; the existing training/checkpoint paths
  cannot use this persistence-only wrapper to bypass streamed-training approval.
- Decoder bundles use tokenization contract version 3 and an explicit
  initialization_check stage. Pipeline interfaces identify reviewed stream inputs,
  initialization-only pretraining and CPU persistence evaluation. Loader checks
  exact approval scope, zero updates, default context 16 / width 8 / seed 7 and
  every parameter against fresh initialization; modified/trained parameters or
  training-stage relabeling reject. Existing tokenization v1/v2 bundles retain their
  prior loading behavior. Resource reserves are checked before creating new files;
  existing artifacts are never overwritten. Failed unpublished checks preserve
  their private files without publishing a success report.
- Native verification rebuilt/launched macOS on port 28857. Cancelling persistence
  consent created no directory. Confirmed checks saved/reloaded Unigram 64-ID
  bundle 44329a7553b74eaca0af9cf3ff929037, iterative byte-BPE 260-ID bundle
  336252e9db174b87ab9bcb3779a125b0 and character-BPE 64-ID bundle
  6cb0306fbc7f44cdbfe7e7ac9d90ad08. Each reported tokenization version 3, exact
  parameter equality and CPU output error 0. The 260-ID model used architecture
  version 2; the 64-ID models used architecture version 1. Every check performed
  zero optimizer updates and retained false training/release/quality approvals.
- Restarting both backend and app reopened each exact report from Saved persistence
  checks. Independent bundle reloads reconstructed all source token IDs and previews,
  reproduced CPU outputs from fresh initializers and verified all approval/hash
  bindings. All 12 new bundle/report files stayed byte-identical across restart,
  as did all 69 prior stream source/candidate/tokenizer/comparison/window/diagnostic
  files. The earlier trained 320-ID tokenization-v2 bundle and step-50 checkpoint
  also loaded unchanged. Fresh check weights remain private artifacts outside Git.
- Validation: 505 Python tests with Metal checks and warnings as errors, 39 Flutter
  tests, clean Flutter analysis/diff checks and successful native builds. Added
  tests cover all streamed codec families, exact parameter/output round trips,
  approval/stale-batch/post-save-source guards, preview bounds, policy and stage
  tampering, modified-weight rejection, checkpoint/training exclusion, maximum
  512-ID persistence and tokenization downgrade rejection. Evidence remains outside
  Git at /tmp/almg-stream-persistence-native-qa/verification.json, *-ui.json/*-ui.txt,
  artifact fingerprints and native build/restart/test logs.
- Remaining: separately approved durable streamed student optimization, checkpoint
  recovery and trained-model/tokenizer persistence/inference; broader acceptance.
  These initialization-only bundles establish an artifact contract, not usable
  trained student models. Independent physical/Windows/larger-than-RAM blockers
  remain open and skipped. No external collection, downloads, generated artifacts/
  weights in Git or push; unrelated edits and prior training artifacts are preserved.

P3-LMF-03 partial progress · approved manual streamed training checkpoints · 2026-11-20:
- [ ] P3-LMF-03 remains open. The learned-window inspector now offers a separate
  “Approve manual streamed trial” action and saved trial history. Explicit consent
  binds the completed source/overlap review, exact codec/windows, runtime, code and
  fixed seed-7 tiny-decoder settings. Approval initializes a private checkpoint;
  each “Run next five updates” executes five masked SGD updates immediately and
  pauses at a saved boundary, up to 20 updates. Four successive training windows
  per update cycle from the beginning; this is a bounded manual trial, not a full
  corpus training run or idle/AC scheduler.
- Each boundary publishes a new immutable model/tokenizer bundle before atomically
  advancing its state pointer. Receipts bind the source-batch chain, next cursor,
  cumulative real-target loss, prior checkpoint hash and final evaluation hash.
  Replayed requests cannot advance twice; source/runtime/code changes and resource
  failures stop continuation. Failed publication preserves the previous checkpoint
  and private unpublished files. A distinct tokenization-v4 contract permits these
  approved trained weights; v3 initialization-only bundles retain their fresh-seed,
  zero-update checks and cannot be promoted by toggling approval flags.
- Final evaluation exhausts every saved validation/test window in batches of at
  most 16 with masked, token-weighted metrics and no held-out optimizer updates.
  The fixed 80% accuracy target is recorded independently; release remains false.
  No external collection, pretrained download or general scheduling was enabled.
- Local app evidence: rebuilt and ran ALMG on this Mac against local fixture
  backend port 28858. Cancel created no additional trial. Approved Unigram trial
  c0c63517b3a049dfa9e5462ab4c284d2 saved five updates, survived a complete app/backend
  restart with identical saved state, then resumed through 10/15/20 updates.
  Native byte-BPE trial 1a7d904877ba4428b77f996b6c960428 (260 IDs, architecture v2)
  and character-BPE trial 7ccb884e596849afbb38d91ab39b83f8 (64 IDs, architecture v1)
  also completed 20 updates. Each changed all nine parameter tensors and saved
  five reloadable model/tokenizer checkpoints. CPU/Metal maximum differences were
  1.03e-7, 9.22e-8 and 4.84e-8 respectively; stored CPU outputs reloaded exactly.
- Verified full held-outs: Unigram 298 validation windows/4404 targets and 273 test
  windows/4055 targets; byte BPE 569/8732 and 522/8028; character BPE 187/2921 and
  174/2713. Test accuracies were about 16.9%, 61.8% and 4.6%, so all correctly kept
  quality_target_met=false and release_approved=false. All three completed reports
  reopened identically after another app/backend restart. All 81 prior stream
  files, old trained byte-BPE bundles and earlier checkpoints remained byte-identical.
- Verification: 508 Python tests passed with real Metal enabled and warnings as
  errors; 40 Flutter tests passed; Flutter analysis and diff checks were clean.
  Tests cover consent/stale reviews, restart/resume equivalence within 1e-6 for
  independent float32 Metal runs, duplicate requests, source changes, immutable
  earlier checkpoints and failed state publication. Evidence is under
  /tmp/almg-stream-training-native-qa/ (native JSON, verification.json, restart
  captures and test/build logs); generated files and weights are outside Git.
- Remaining: broader tokenizer acceptance, production-scale streamed training,
  general streamed-model inference/export and scheduler integration. P3-LMF-01
  is already complete. Unchanged physical power, Windows and oversized-fixture
  blockers remain open and skipped; unrelated user edits were preserved.

P3-LMF-03 partial progress · saved streamed-model private CPU previews · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed manual streamed trials now offer “Preview
  saved model”. The native dialog explains the short trial's poor/unestablished
  quality, local prompt/output storage, 16-token prompt limit and twelve-token
  greedy CPU generation. Generation requires the explicit “Generate and save
  private preview” action; opening/closing the dialog saves nothing. Generated
  text appears first, with whitespace-only output identified and a separate
  expandable saved-record panel. This grants no training or model release.
- Inference loads the exact tokenization-v4 checkpoint and saved full-split codec;
  it preserves prompt whitespace, rejects unsupported or over-context prompts
  without truncating or refitting, uses a sliding 16-token context, and checks
  finite scores. The API supports 1–32 new IDs; the native action requests 12.
  Generated byte sequences follow the saved replacement-character display policy.
  The completed run revision, source/permission/overlap bindings and checkpoint
  integrity are rechecked before publication. Stale/incomplete trials are refused.
- Preview records live separately from immutable training state and checkpoints,
  bind exact prompt/generated IDs, tokenizer/checkpoint/run hashes and CPU inference
  policy, and have bounded atomic publication plus hash-checked saved history.
  History review also rechecks current source permission/integrity. No optimizer,
  external collection, Qwen request or pretrained download is used.
- Local app verification: rebuilt and ran ALMG on this Mac using fixture backend
  port 28859. The native Unigram dialog rejected both an unsupported “banana”
  prompt and an over-16-token prompt without saving records. All three completed
  Unigram, byte-BPE and character-BPE trials generated and saved twelve IDs from
  the exact prompt “ unique ”, including both surrounding spaces. Captured IDs
  and decoded text matched independent reloads of the saved model/tokenizer.
  Original previews 0c0de1a9, 7fed2903 and 86d068cc reopened identically after
  complete app/backend restart; generation again produced identical IDs/text.
  The final readable-output/expandable-record layout was exercised in the native
  app for all three families. quality_target_met and release_approved stayed false.
- All 136 prior stream/source/model/checkpoint files and original preview files
  remained byte-identical. 511 Python tests passed with real Metal fixture
  training and warnings as errors; 41 Flutter tests passed; Flutter analysis and
  diff checks were clean. Tests cover consent/input limits, incomplete/stale runs,
  exact whitespace, deterministic restart/history, corrupt-history rejection,
  source changes before publication and unchanged trained weights. Evidence is in
  /tmp/almg-stream-preview-native-qa/ (verification.json, native/restart captures,
  negative-prompt UI captures and test/build logs); private data stays outside Git.
- Remaining: private streamed-model export/import, production-scale training,
  broader tokenizer acceptance and general scheduler integration. P3-LMF-01 is
  already complete; unchanged physical power, Windows and oversized-fixture
  blockers remain open and skipped. Unrelated user edits and weights are preserved.

P3-LMF-03 partial progress · independent saved-stream CPU evaluation · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed streamed trials now offer “Re-evaluate saved
  model”. Opening/closing the native dialog performs no evaluation; “Evaluate
  saved model on CPU” explicitly reloads the immutable model/tokenizer and saves
  a new private evaluation report. The main display shows split populations,
  real-target counts, accuracy, loss and whether both splits meet the 80% target;
  detailed provenance is expandable. Neither a passing nor a failing report grants
  training, export approval or model release.
- The independent NumPy scorer exhausts every saved validation/test window in
  batches of at most 16, excludes padding and aggregates by real target tokens.
  Reports bind the exact completed trial/checkpoint, tokenizer/windows revisions,
  CPU runtime, evaluation version and implementation hash, and compare accuracy
  and loss with the original Metal evaluation. Current source/permission/overlap
  and checkpoint integrity are checked before and after scoring. Nonfinite scores,
  stale/incomplete trials and publication/source failures save no partial report.
  Reports are separate, bounded, atomically published and hash-checked in history;
  frozen weights, training state, earlier reports and preview history are untouched.
- Local app verification: rebuilt and ran ALMG on this Mac using fixture backend
  port 28860. Canceled the Unigram evaluation dialog without creating a report,
  then evaluated all three saved full-split codec families through native controls.
  CPU report 71b6119a covered Unigram validation 298 windows/4404 targets and test
  273/4055; f9497a3d covered byte BPE 569/8732 and 522/8028; c96f3ef3 covered
  character BPE 187/2921 and 174/2713. CPU accuracies matched the original Metal
  values exactly; maximum absolute loss differences were 1.59e-7, 5.88e-8 and
  1.56e-7 respectively. All correctly reported passed=false and release=false.
- After a complete app/backend restart, all three original reports reopened
  identically in native saved history and fresh CPU evaluations reproduced exactly
  the same metrics. All 145 prior stream/source/model/checkpoint/preview files and
  original report files remained byte-identical. 514 Python tests passed with real
  Metal fixture training and warnings as errors; 42 Flutter tests passed; Flutter
  analysis and diff checks were clean. Tests verify consent/stale/incomplete gates,
  full populations, nonvacuous padding-target invariance, restart/history, nonfinite
  scores, source changes and failed atomic publication without weight changes.
  Evidence: /tmp/almg-stream-evaluation-native-qa/ (verification.json, native and
  restart captures, consent UI, test/build logs). Generated/private files stay out
  of Git; no external requests or pretrained downloads were used.
- Remaining: streamed-model archive export/import, production-scale training,
  broader tokenizer acceptance and scheduler integration. Current short trials
  remain below the export flow's 80% evaluation target; this gate was preserved.
  Repeating unchanged evaluations is unnecessary unless checkpoint/evidence changes.
  P3-LMF-01 is already complete. Unchanged physical power, Windows and oversized-
  fixture blockers remain open and skipped; unrelated edits and weights are preserved.

P3-LMF-03 partial progress · reviewed private streamed-checkpoint ZIP export · 2026-11-20:
- [ ] P3-LMF-03 remains open. Completed streamed trials now offer “Export private
  streamed model”. A separate native review explains that weights, exact tokenizer
  pieces and saved prompt/output may be private. A saved passing independent CPU
  evaluation and saved preview are mandatory; fresh read-only CPU evaluation and
  preview reproduction must match those receipts. The existing 80% target is kept.
  Failing models, missing receipts, stale reviews and changed checkpoint/source
  bindings cannot export. Neither passing evaluation nor export grants release.
- The versioned private streamed archive contains exactly decoder.json,
  tokenizer.json and manifest.json under bundle/, plus evaluation.json,
  preview.json and export-manifest.json. Reviewed file hashes bind the exact
  checkpoint and receipts; raw source documents, indexes, databases, other
  checkpoints and unrelated history are excluded. The archive is limited to
  8 MiB, stores an immutable SHA-256 receipt and ZIP atomically outside Git, and
  is returned only after explicit destination approval. Canceling the native
  destination picker creates no archive. Existing evaluation/preview APIs retain
  their default persistence; export review uses an internal read-only option.
- Local app verification: rebuilt and ran ALMG on this Mac with fixture backend
  port 28861. The original below-target Unigram trial was refused with “80%
  evaluation target; private export is unavailable”. A separate local, deliberately
  simple pipeline fixture used 121 short repetitive records, a complete 256-ID
  whole-split byte codec and real 20-step Metal training. Trial 897f8817 achieved
  validation 590/610 targets (96.72%) and test 1003/1039 (96.54%) in independent
  CPU evaluation. This contrived fixture verifies the gate/export mechanism,
  not useful language modeling or semantic generalization; release stayed false.
- In the native app, reviewed that passing trial's exact archive contents, canceled
  the save picker without creating an export, then approved the local QA directory
  and saved private-stream-decoder-897f8817.zip. The 52,315-byte download matched
  its persisted receipt, all five reviewed payload hashes and the versioned export
  envelope. Archive ID
  06587ce4ad4040ac886a42046e00b7ce has SHA-256
  2686ecb41cefcaf81049eefdc7f480139efa7df38318e9520cc39b386a9223f2.
  Reloading its exported tokenization-v4 bundle preserved exact codec artifacts
  and CPU outputs. Legacy bounded-trial import correctly rejected this new format;
  streamed-archive import remains explicitly unavailable in the UI.
- After complete app/backend restart, the native export review reproduced exactly,
  and the ZIP, receipt, destination copy and all 154 prior stream/source/model/
  checkpoint/preview/report files remained byte-identical. 517 Python tests passed
  with real Metal fixture training and warnings as errors; 43 Flutter tests passed;
  Flutter analysis and diff checks were clean. Tests cover consent, failing quality,
  missing receipts, read-only review, stale approval, destination cancellation,
  reviewed hashes and exact reloadable contents. Evidence is under
  /tmp/almg-stream-export-native-qa/ (native review/save captures, verification.json,
  ZIP, restart checks and test/build logs); generated artifacts are outside Git.
- Remaining: isolated streamed-archive import/restart/inference verification,
  production-scale training, broader tokenizer acceptance and scheduling. The
  original short trials still fail the quality gate and remain ineligible for
  export. P3-LMF-01 is already complete; unchanged physical power, Windows and
  oversized-fixture blockers stay open and skipped. Unrelated edits and weights
  are preserved; no external collection, pretrained downloads or push occurred.

P3-LMF-03 acceptance complete · isolated streamed-archive import and CPU preview · 2026-11-20:
- [x] P3-LMF-03 — Tokenizer Engine acceptance is complete for the implemented,
  explicitly bounded configurable profiles and reviewed streamed workflows.
  Earlier partial-progress entries above remain historical evidence. Production-
  scale pretraining, scheduling, broader architecture generation and Model Library
  integration are separate requirements, rather than additional tokenizer-engine
  acceptance criteria. Existing vocabulary/context/source-size limits remain explicit.
- Delivered this change: recipe details and learned-input inspectors now offer
  “Import private streamed archive”. Native selection alone imports nothing; an
  explicit confirmation copies a validated archive into a new isolated namespace.
  The UI labels archived evaluation claims as unverified because source documents
  are excluded. Training and release remain unavailable. CPU previews preserve exact
  prompt whitespace, enforce the saved 16-token context, generate 1–32 IDs (12 in
  the UI), use the saved byte-display policy, and save at most five private previews.
- The importer admits exactly the six versioned streamed ZIP members, limits the
  archive to 8 MiB and each expanded member separately, and rejects extra/traversing
  paths, links, encryption, unsupported compression, changed hashes/receipts and
  non-reproducing archived previews. It validates the tokenization-v4 completed
  checkpoint, matching model/tokenizer/receipt bindings and archived metric shape,
  without treating those archived scores as a fresh dataset evaluation. Publication
  is atomic; failed imports leave no published record. Reload verifies payload
  hashes and configuration; bounded preview state updates are atomic and serialized.
- Local app verification: rebuilt and ran ALMG on this Mac using backend port
  28862. Canceled native selection without creating an import, selected the real
  52,315-byte private-stream-decoder-897f8817.zip, verified the pending confirmation,
  then explicitly imported it as 5bff22e5bf8c48cb8923f039565efaae. Archive SHA-256
  remained 2686ecb41cefcaf81049eefdc7f480139efa7df38318e9520cc39b386a9223f2.
  Generated twelve CPU IDs from the exact prompt “ aaaa ”, including both spaces.
- Restarted the app/backend using a fresh receiver directory containing only the
  imported model plus UI fixture carriers: no original training run or source text
  index existed there. Native saved-import history reopened the exact prior record;
  a second preview produced identical IDs/text and saved the second history entry.
  All six imported payloads retained their hashes, all 186 prior stream/source/model/
  checkpoint/preview/report/export files stayed byte-identical, and the first
  imported copy stayed unchanged. Import status remained
  archived_claims_not_re_evaluated_source_excluded, training_approved=false and
  release_approved=false. No external collection, model download or release ran.
- Acceptance audit (all five criteria verified):
  1. User-approved tokenizer fitting: native bounded BPE/character-BPE/Unigram
     experiments and separately approved resumable full-training-split fits were
     verified in the preceding tokenizer fitting/comparison entries.
  2. Representative encoding/decoding: multilingual/Unicode round trips, explicit
     unknown-token behavior and lossless-only statistics/comparisons passed; special
     PAD/BOS/EOS/UNK definitions and lossy UNK disclosure were verified in
     /tmp/almg-special-token-native-qa/verification.json and current regression tests.
  3. Configuration saved with a model: the special-token adoption dataset,
     100-step trained model and step-50 checkpoint currently reload with identical
     tokenizer SHA-256 a58efbf6a64236b01346353eedbfde0a7d4f4eeba1a8bbb5895f1a01ecafb634
     and PAD/BOS/EOS IDs 57/58/59. All three trained full-split codec families also
     reload exact tokenization-v4 artifacts with their actual vocabularies.
  4. Invalid/incompatible configurations rejected before pretraining: native
     compatibility/adoption rejection evidence and current tests cover stale/source
     changes, lossy/unknown coverage, vocabulary/capacity, special-ID collisions,
     model dimensions, permissions and contaminated held-outs.
  5. Restart reload: earlier native bounded/special-token and all three streamed
     codec/model restart checks passed; this change additionally verified source-
     independent streamed archive import and inference after native app restart.
- Verification: 520 Python tests passed with real Metal fixture training and
  warnings as errors; 44 Flutter tests passed; Flutter analysis and diff checks
  were clean. Added tests cover consent/limits, isolated restart/exact prompts,
  corrupt payloads, self-consistent but non-reproducing receipts, linked/extra/
  oversized members, integrity failure and failed atomic publication. Evidence:
  /tmp/almg-stream-import-native-qa/ (verification.json, tokenizer-acceptance-audit.json,
  native selection/confirmation/preview/restart captures and build/test logs).
  Private files and generated weights remain outside Git. Unrelated user edits,
  old imports/exports and downloaded weights are preserved. P3-LMF-02 physical
  power/Windows/oversized-fixture blockers remain open and skipped; continue with
  the next independently actionable requirement in document order.

P3-LMF-04 partial progress · validated pre-allocation architecture plans · 2026-11-20:
- [ ] P3-LMF-04 remains open. Recipe details now offer “Plan decoder architecture”.
  Structured version-1 plans validate layer count, hidden width, attention heads,
  head dimension, feed-forward width, context, vocabulary, seed and planning batch
  size before allocation. Unknown/missing fields, booleans in numeric fields,
  out-of-range dimensions, hidden_size != heads × head_dim and FF width below
  hidden width are rejected. Native presets and an explicit bounded head selector
  make the supported layouts reviewable; editing fields invalidates save approval.
- Plans explicitly describe bias-free dense decoder layouts with untied head/input
  embeddings, learned absolute positions, parameter-free LayerNorm, ReLU and
  normal(0, 0.02) initialization. Other strategies are rejected in this version.
  Per-tensor shapes and exact calculated parameter counts are produced without
  constructing weights: 2*vocab*hidden + context*hidden + layers*(4*hidden^2 +
  2*hidden*feed_forward). Supported planning bounds are 1–8 layers, hidden 8–128,
  1–8 heads, head dimension 2–64, FF width 8–512, context 2–256 and vocabulary 4–512.
- Memory output separates FP32 weights, gradients, two Adam moment tensors and a
  retained activation-layout estimate. Every estimate is explicitly unmeasured;
  workspace, allocator and runtime/framework memory are excluded, so this is not
  a feasibility guarantee. The UI and saved schema state plan-only,
  weights_allocated=false, execution_available=false and no training/release
  approval. Review creates no files. Saving requires explicit approval of the
  exact code/configuration review and atomically publishes only plan.json.
- Local app verification: rebuilt and ran ALMG on this Mac against local fixture
  backend port 28863. A two-layer configuration with width 16, three heads and
  head dimension 8 was rejected before saving. Reviewed the tiny single-layer
  preset (1,664 parameters, 6,656 FP32 weight bytes), then closed it without any
  saved artifact. Explicitly saved the valid two-layer/two-head preset as
  5373ba6fc55b40f8821266ce4c5973d3: 15 planned tensors, 8,704 parameters, 34,816
  weight bytes, 34,816 gradient bytes, 69,632 Adam moment bytes, 327,680 activation
  layout bytes and 466,944 total training-layout bytes. No model was initialized.
- After complete app/backend restart, native saved-plan history reopened the exact
  configuration, shapes, counts, estimates and flags. Only plan.json existed in
  the new artifact directory; all prior imported-model payloads/history stayed
  byte-identical. Tests independently compare the legacy-compatible plan's every
  tensor shape, actual parameter count and actual weight bytes with the existing
  Decoder, verify multilayer/head arithmetic without constructor calls, reject
  invalid configurations and stale consent, and cover restart/tamper and failed
  atomic publication. This validates planning, not execution of the new layouts.
- Verification: 524 Python tests passed with real Metal regression fixtures and
  warnings as errors; 45 Flutter tests passed; Flutter analysis and diff checks
  were clean. Evidence: /tmp/almg-architecture-plan-native-qa/ (native invalid,
  tiny-review, saved/reopened plan JSON and UI captures, restart verification and
  test/build logs). Plans and generated artifacts are outside Git; no external
  requests, pretrained downloads or changes to existing trained weights occurred.
- Remaining acceptance: construct/initialize the configurable architecture from
  its approved plan, execute and validate forward/backward passes for those
  layouts, persist/reload initialized architecture/weights, and report the actual
  constructed parameter count alongside the declared memory estimates.
  P3-LMF-03 stays complete. Unchanged P3-LMF-02 hardware/Windows/oversized-fixture
  blockers remain open and skipped; unrelated user changes are preserved.

P3-LMF-04 partial progress · fresh multilayer/multihead CPU models and persistence · 2026-11-20:
- [ ] P3-LMF-04 remains open. Saved architecture plans now offer a separate
  “Initialize fresh planned model” confirmation and saved initialization history.
  Confirmation binds the exact immutable plan and checks memory/disk reserves
  before allocation. New seeded NumPy weights are independent of Qwen/downloaded
  checkpoints. The plan itself remains a layout artifact; initialized models and
  CPU evidence are published separately, without training or release approval.
- The new versioned PlannedDecoder implements the reviewed layer/head dimensions:
  per-layer Q/K/V projections, head splitting, scaled causal attention, head merge,
  residual attention/FF blocks, learned absolute positions, parameter-free layer
  normalization, ReLU and an untied output head. Configuration validation precedes
  RNG/allocation. Actual tensor count, actual parameter count and actual FP32
  parameter bytes must equal the reviewed layout. Existing legacy decoder recipes,
  artifact formats, tokenizer bundles and trained checkpoints are unchanged.
- Each initialization runs a bounded synthetic CPU batch, checks finite logits and
  causal-prefix invariance after changing future IDs, saves a JSON model artifact without
  executable serialization, reloads every parameter and requires exactly identical CPU output.
  Artifact loading validates format, configuration, parameter names/shapes, numeric
  values and FP32 bounds. Initialization history additionally verifies every tensor
  against the fresh seeded plan, so trained/modified weights cannot be relabeled
  as a zero-update initialization. Publication is atomic and preserves prior files.
- Local app verification: rebuilt and ran ALMG on this Mac with fixture backend
  port 28864. Canceled initialization without creating weights, then explicitly
  initialized three saved layouts through native controls:
  - Tiny one-layer/one-head: plan 14596499, initialization 6e292eb5, 9 tensors,
    1,664 parameters, 6,656 FP32 weight bytes and output shape [2,8,64].
  - Two-layer/two-head: plan 5373ba6f, initialization a8ec93ad, 15 tensors,
    8,704 parameters, 34,816 bytes and output shape [2,8,128].
  - Four-layer/four-head: plan fb3aa5aa, initialization d030e1a2, 27 tensors,
    270,336 parameters, 1,081,344 bytes and output shape [2,8,512].
  All had zero causal-prefix error and zero immediate CPU reload difference;
  every parameter reloaded exactly. Backward checks remained false, optimizer
  updates zero, pretrained_weights_loaded=false and training/release flags false.
- After complete app/backend restart, all three original records and full CPU
  forward arrays matched exactly. A new native seed-7 initialization of the same
  two-layer plan produced an identical model SHA-256
  f66f3013d8255302fb96044f2ff443a088eb538b2f425c1a876cfc99b8da56f3.
  All eight prior imported-model/plan files and the six original initialization
  files remained byte-identical. Actual parameter bytes exclude allocation/runtime
  overhead; the NumPy reference uses float64 forward intermediates. The inherited
  FP32 training-layout estimates remain explicitly unmeasured and are not a CPU
  peak-memory measurement or training-feasibility guarantee.
- Verification: 528 Python tests passed with real Metal legacy regression fixtures
  and warnings as errors; 46 Flutter tests passed; Flutter analysis and diff checks
  were clean. New tests compare vectorized multihead/multilayer math against a
  separate per-head reference, compare the one-head formula against legacy math,
  verify seed identity/difference and causality, reject invalid inputs before RNG,
  enforce consent/stale/resource gates, preserve exact reloads, reject rehashed
  modified parameters and recover failed publication. Evidence is under
  /tmp/almg-architecture-init-native-qa/ (native consent/initialization/restart JSON,
  verification.json, saved probe arrays and build/test logs). Generated weights and
  artifacts are outside Git; no external collection or pretrained download ran.
- Remaining acceptance: execute and validate a backward pass for these configured
  architectures, including finite gradients and a meaningful small-batch numerical
  check. Training engines and quality/release remain separate requirements.
  P3-LMF-03 stays complete; unchanged hardware/Windows/oversized-fixture blockers
  remain open and skipped. Unrelated user edits and previous weights are preserved.

P3-LMF-04 acceptance complete · configurable architecture backward validation · 2026-11-20:
- [x] P3-LMF-04 — Neural Architecture Generator acceptance is complete for the
  implemented bounded decoder profile. Earlier partial entries remain historical
  evidence. Supported policies remain explicit: bias-free dense attention/FF,
  learned absolute positions, parameter-free LayerNorm, ReLU, seeded normal(0,.02)
  initialization and the documented geometry bounds. Other positional/norm/
  activation policies and GQA/MoE/recurrent/multimodal extensions remain unsupported
  and planned; this completion does not claim those extensions or production training.
- Delivered this change: saved initialized architectures now offer a separate
  “Check planned-model backward pass” confirmation and saved diagnostic history.
  It loads the exact unchanged seeded model and runs five temporary Metal SGD
  updates (learning rate .05) on a bounded synthetic next-token batch. Every
  gradient bank must be finite and nonzero, every tensor must change during the
  diagnostic, loss must decrease, and CPU/Metal logits must agree within 1e-5.
  Updated weights are discarded; only a versioned report is published. Original
  initialization receipts remain immutable forward-only historical records.
- Masked padding targets are changed nonvacuously where the batch/context permits
  padding, with loss/gradient differences limited to 1e-6. For the minimum one-row,
  two-position configuration, both targets are retained so attention gradients
  stay nonvacuous and padding is explicitly reported not applicable. Three selected
  gradient coordinates (output head, first attention query, last FF input) are
  independently checked by CPU central finite differences at epsilon .001, using
  absolute tolerance 1e-6 + .02*max(abs(analytic),abs(numerical)). This is selected
  numerical validation, not an exhaustive numerical derivative for every parameter.
- Local app verification: rebuilt and ran ALMG on this Mac using fixture backend
  port 28865. Canceled the first backward confirmation without creating a report,
  then ran actual Metal checks from saved models through native controls:
  - One-layer/one-head report 6fea2bd1: all 9 tensors changed; synthetic loss
    4.14838171 → 3.93458009; final CPU/Metal maximum difference 3.49e-8.
  - Two-layer/two-head report 06509fb7: all 15 tensors changed; loss
    4.83195829 → 4.39381504; final CPU/Metal maximum difference 6.36e-8.
  - Four-layer/four-head report 24a63517: all 27 tensors changed; loss
    6.32929897 → 4.90557861; final CPU/Metal maximum difference 4.24e-7.
  Each had two changed padded targets, invariant masked loss/gradients and all
  three finite-difference probes within the declared tolerance. No updated weights,
  training approval, model quality claim or release was produced.
- After complete app/backend restart, all three saved reports reopened exactly.
  Repeating the two-layer diagnostic reproduced initial/final losses within 1e-5.
  All 18 prior initialized model/plan/import files and the three original reports
  remained byte-identical. Report retrieval rechecks source initialization revision,
  model hash and the seeded-weight invariant; failed numerical/source/publication
  checks save no partial report and never overwrite the source model.
- Acceptance audit (all six criteria verified):
  1. Structured architecture generation: versioned plans validate and construct
     configured layers, widths, head counts/dimensions, FF/context/vocabulary and
     seed/policy fields; native one-/two-/four-layer layouts execute successfully.
  2. Independent initialization: native fresh-weight confirmation and seed identity/
     difference tests verify new NumPy weights with no Qwen/downloaded checkpoint.
  3. Forward/backward execution: saved-model CPU finite/causal forward checks plus
     actual Metal autodiff, gradient finite differences and decreasing synthetic
     loss passed for all three native layouts and the minimum context/batch test.
  4. Invalid dimensions: native hidden/head mismatch and current strict-schema,
     type/bounds, input-ID/context and pre-allocation rejection tests passed.
  5. Architecture persistence: native plan/config/model/parameter/forward-array
     save/reload and restart checks passed; original seeded artifacts stay intact.
  6. Counts/memory: actual tensor/parameter counts and FP32 bytes match each reviewed
     layout, including 270,336 parameters/1,081,344 bytes for four layers/four heads.
     FP32 training-layout estimates remain labeled calculated/unmeasured, excluding
     workspace/allocator/runtime overhead. Peak-memory profiling belongs to hardware
     feasibility; no estimate is presented as a measured training guarantee.
- Verification: 532 Python tests passed with real Metal enabled and warnings as
  errors; 47 Flutter tests passed; Flutter analysis and diff checks were clean.
  Added tests cover approval/staleness, all native layouts, masked targets, minimum
  context/batch, deliberately wrong-gradient rejection, immutable initialized
  weights, report restart and failed publication. Evidence is under
  /tmp/almg-architecture-backward-native-qa/ (verification.json, native consent,
  reports/restart captures, prototype diagnostics and test/build logs).
  Generated/private files and weights are outside Git. P3-LMF-03 remains complete;
  unchanged physical power/Windows/oversized-fixture blockers stay open and skipped.
  Continue with the next independently actionable requirement in document order;
  unrelated user changes, old artifacts and downloaded weights are preserved.

P3-LMF-05 partial progress · hardware review for planned-model backward diagnostics · 2026-11-20:
- [ ] P3-LMF-05 remains open. Added a local hardware feasibility report before
  confirming the bounded synthetic architecture backward check. It records Apple
  silicon memory, available memory/disk, MLX/Metal device information and the
  selected precision. Unsupported precision/device choices cannot execute, and
  resources are checked again immediately before model loading/execution.
- Calculated FP32 parameters, gradients, transient copies, activation layout,
  CPU reference/loading and disk reserves are explicitly estimates. SGD moment
  storage and imported dataset storage are zero for this synthetic-only scope.
  Low-memory fixtures produce a smaller valid plan suggestion without changing
  the approved plan. No measured peak memory or duration prediction is claimed.
- New v2 diagnostic records retain the observed hardware/feasibility snapshot
  and approval revision; existing v1 records remain readable and immutable.
- Local verification: rebuilt and exercised the native macOS ALMG app on Apple
  M4 Max using isolated local fixtures. Opened a supported float32 report,
  selected float16 and observed the blocker with no confirmation action, cancelled,
  reopened float32 and explicitly approved five Metal steps. Loss decreased from
  4.831958293914795 to 4.393815040588379; updated weights were discarded. Restarted
  both app and fixture backend, then reopened new report f579a7efd4ca4bfb820c92d294eec1aa
  and legacy report 06509fb756994f54af127c2e78f57fd9 with exact saved-record equality.
  All 22 pre-existing architecture fixture files retained their SHA-256 hashes.
- Regression evidence: 536 Python tests passed with actual Metal enabled and
  warnings treated as errors; 48 Flutter tests passed; Flutter analysis clean.
  Tests include read-only preflight, low-memory recommendations, unsupported
  precision/device rejection, stale approvals and changing resource availability.
  Local evidence: /tmp/almg-architecture-feasibility-native-qa/verification.json.
- Remaining: full dataset-training feasibility/approval integration, measured
  peak-memory trials that update estimates, duration prediction, and Windows/CUDA
  verification on suitable hardware. P3-LMF-01 is already complete for its recorded
  bounded architecture scope. Unchanged blocked items remain open and skipped.
  No external collection, downloads, generated artifacts or weights are committed.

P3-LMF-05 partial progress · synchronized diagnostic memory and timing observations · 2026-11-20:
- [ ] P3-LMF-05 remains open. Five-step planned-decoder backward diagnostics now
  save synchronized active Metal memory samples, baseline/incremental values,
  process peak counters before/after, and elapsed diagnostic time. Shared peak
  counters are not reset or attributed solely to this diagnostic. Samples exclude
  cached buffers and CPU memory and may miss transient peaks; elapsed time includes
  CPU numerical checks and must not be interpreted as optimizer throughput.
- Compare sampled incremental memory with the original calculated GPU estimate,
  flag observed overruns and retain a conservative observed budget that never
  falls below that estimate. This is saved diagnostic feedback; no automatic
  admission relaxation, isolated trial peak or full-training prediction is claimed.
- New v3 diagnostic records include these observations. Existing v1 and v2 formats
  remain readable without rewriting historical reports or source model weights.
- Native local evidence: rebuilt macOS ALMG on Apple M4 Max, reviewed feasibility
  and explicitly confirmed five synthetic Metal steps. Report b9a7de8599db4957a99690f90e6e4d68
  recorded seven synchronized samples, 0.10714379092678428 seconds elapsed,
  139728 sampled incremental active Metal bytes, and process peak 0 -> 248048
  bytes, versus a calculated 167936-byte GPU working estimate. The UI showed the
  measurements, comparison and limitations. Loss fell 4.831958293914795 ->
  4.393815040588379; updated weights were discarded. After app and fixture backend
  restart, new v3 and existing v1/v2 reports reopened with exact saved-record
  equality; all 23 pre-existing architecture fixture files retained their hashes.
- Verification: 538 Python tests passed with actual Metal enabled and warnings as
  errors; 48 Flutter tests passed; Flutter analysis and diff checks clean. Added
  tests cover shared-counter semantics, estimate overruns, nonnegative increments,
  retaining conservative estimates, actual Metal samples and v1/v2 compatibility.
  Evidence: /tmp/almg-diagnostic-measurements-native-qa/verification.json and logs.
- Remaining: isolated per-trial peak measurement including CPU/loading overhead,
  measured calibration for full dataset training and duration prediction, training
  approval integration, and Windows/CUDA verification on suitable hardware. Existing
  hardware/user-action blockers remain open and skipped. No generated artifacts,
  private data, weights or unrelated user edits are included in this commit.

P3-LMF-05 partial progress · isolated synthetic diagnostic peak measurements · 2026-11-20:
- [ ] P3-LMF-05 remains open. Approved architecture backward checks now execute
  in a fresh local Python process with a separate Metal allocator peak counter.
  Reports capture that process's Metal peak, peak resident memory including
  interpreter/imports/source loading/CPU checks, and workflow elapsed time.
  RSS and Metal peak are displayed separately because unified-memory usage can
  overlap; Metal allocator measurements exclude cached buffers. Workflow time
  excludes interpreter/import startup and is not a full-training prediction.
- Compare the isolated Metal peak with the calculated GPU working estimate and
  retain the larger value as observed diagnostic budget feedback. Parent and
  worker recheck feasibility; the worker cannot publish. The parent validates
  the returned record and rechecks unchanged initialization before atomic save.
  Worker errors, malformed results and timeouts publish no report. No updated
  model weights are stored and no training/release approval is granted.
- New v4 reports add isolated measurements; v1/v2/v3 historical reports remain
  readable and immutable. Shared-process direct diagnostic results are still
  identified as shared rather than mislabeled isolated measurements.
- Local native verification: rebuilt and ran macOS ALMG on Apple M4 Max with
  isolated local fixtures, reviewed feasibility and confirmed five Metal steps.
  Report 811e15baec64429bb8ce8acd7113e070 recorded worker PID 22857,
  separate from fixture backend PID 22137, Metal peak 254912 bytes,
  peak RSS 67354624 bytes and workflow elapsed
  0.21786929201334715 seconds. Metal peak exceeded the calculated
  167936-byte estimate; the UI flagged the overrun and showed an observed
  budget of 254912 bytes with measurement limitations.
  Synthetic loss fell 4.831958293914795 -> 4.393815040588379. After restarting
  app and fixture backend, new v4 and all three historical formats reopened with
  exact saved-record equality. All 24 pre-existing fixture artifact hashes held.
- Verification: 540 Python tests passed with actual Metal and warnings as errors;
  final worker validation passed both focused worker tests; 48 Flutter tests passed,
  Flutter analysis clean. Tests cover consent, error/malformed/timeout nonpublication,
  actual separate worker PID/peaks, immutable sources and report compatibility.
  Evidence: /tmp/almg-isolated-diagnostic-native-qa/verification.json and logs.
- Remaining: measured full-dataset training calibration and duration prediction,
  training approval integration, supported-recipe CPU fallback verification and
  Windows/CUDA host verification. The isolated synthetic diagnostic is not proof
  of full-training feasibility. Unchanged hardware/user-action blockers remain
  open and skipped. No private/generated data, weights or unrelated edits committed.

P3-LMF-05 partial progress · measured diagnostic calibration feeds admission · 2026-11-20:
- [ ] P3-LMF-05 remains open. Subsequent architecture feasibility reviews now
  consume compatible saved isolated diagnostic measurements. Matching requires
  the same initialization/model, plan/configuration, Metal hardware and MLX runtime,
  diagnostic implementation hash, valid report/snapshot revisions and isolated
  measurement provenance. Incompatible, shared, corrupted or invalid measurements
  are ignored. Historical high-water observations are retained beyond the UI's
  20-record history display limit; measurements never lower the calculated reserves.
- Reviews retain calculated estimates separately from measured calibration and
  identify source report IDs/revisions. GPU admission uses the larger calculated
  or observed peak, including the Metal working-set check; memory admission uses
  at least the existing reserve and a conservative CPU RSS + GPU peak + base
  reserve. CPU/GPU unified-memory overlap is explicitly disclosed. Changed
  calibration invalidates an old approval, and live resources are rechecked.
  No duration prediction or extrapolation to full dataset training is made.
- New feasibility v2 snapshots retain calibration alongside experiment records;
  older saved feasibility snapshots remain readable without migration or rewriting.
- Native verification: rebuilt and ran ALMG on local Apple M4 Max with isolated
  fixtures. First report f3d37ed2daca4f6daac4b77246d41918 supplied a measured Metal
  peak of 254912 bytes and process RSS of
  65863680 bytes. The next review visibly cited that
  compatible report, raised GPU budget from 167936 to
  254912 bytes and raised the memory reserve from
  271436096 to 334554048 bytes. Explicit approval produced
  second diagnostic edc1fb7529f04386b4715922dbd8f560 carrying that calibration.
  After app/backend restart the saved second report and an older feasibility-v1
  report reopened unchanged, and a fresh review recovered both compatible trials.
  All 27 pre-existing architecture fixture file hashes remained unchanged.
- Verification: 543 Python tests passed with real Metal and warnings as errors;
  48 Flutter tests passed; analysis and diff checks clean. Added tests cover
  read-only calibration, live low-memory blocking, incompatible/tampered/shared
  rejection and retaining an older high-water measurement beyond 20 reports.
  Evidence: /tmp/almg-calibrated-feasibility-native-qa/verification.json and logs.
- Remaining: full-dataset training feasibility/calibration and approval integration,
  training-duration prediction, supported-recipe CPU fallback verification and
  Windows/CUDA verification on suitable hardware. Unchanged hardware/user-action
  blockers remain open and skipped. No generated/private artifacts, weights or
  unrelated user edits are committed.

P3-LMF-05 partial progress · feasibility before bounded streamed-training approval · 2026-11-20:
- [ ] P3-LMF-05 remains open. The existing manual twenty-step streamed SGD trial
  now displays a model-specific hardware feasibility report before approval.
  Read-only preflight binds the exact saved windows/tokenizer/training review,
  detects local Apple silicon/MLX Metal and memory/disk, and calculates FP32
  parameters, gradients, activation layout, zero SGD moment storage, existing
  source/index/window storage and five-checkpoint disk budget without constructing
  a model or copying/materializing a dataset. Estimates and measurement limits
  are explicit; this bounded trial is not full-epoch feasibility.
- HTTP training initialization requires the reviewed feasible report and rechecks
  its bindings and live resources before calling the original training engine.
  Missing/stale approval, unsupported precision/device and inadequate resources
  cannot initialize through this route. Blocked reports hide the approval action;
  cancelling leaves no trial. Existing checkpoint/receipt formats and training
  implementation hashes are unchanged so saved trials remain readable/resumable.
- Native verification: rebuilt and ran local macOS ALMG on Apple M4 Max with
  the existing Unigram stream fixture. The app showed 1664 parameters,
  6656 parameter bytes, 268959744 bytes of memory reserve and
  88912384 bytes of additional disk reserve, including
  21803520 bytes for five checkpoints and 1502462 bytes of
  existing source/index/window storage. Cancel created no trial. Explicit approval
  initialized run 40ac701d379e462a9d673f65e67191f1 and reached a paused five-step checkpoint.
  After app/backend restart it reopened with exact state equality and resumed
  to ten updates. The older completed Unigram trial reopened unchanged; all
  193 pre-existing fixture file hashes remained unchanged.
- Verification: 545 Python tests passed with real Metal and warnings as errors;
  49 Flutter tests passed; analysis and diff checks clean. Tests verify calculated
  parameter bytes against the actual decoder, read-only preflight, consent/stale/
  unsupported and changed-resource rejection before initialization, and hiding
  approval for a blocked report. Evidence:
  /tmp/almg-stream-feasibility-native-qa/verification.json and native/test/build logs.
- Remaining: save hardware approval profiles with streamed experiment records,
  measured streamed-training calibration and duration prediction, feasibility for
  broader/full-epoch training and per-continuation integration, supported-recipe
  CPU fallback verification and Windows/CUDA verification on suitable hardware.
  Unchanged hardware/user-action blockers remain open and skipped. No generated
  artifacts, private data, weights or unrelated user edits are committed.

P3-LMF-05 partial progress · saved hardware approval profiles for streamed trials · 2026-11-20:
- [ ] P3-LMF-05 remains open. Newly approved bounded streamed trials now retain
  both the report the user approved and the fresh resource check taken before
  initialization. A versioned, atomically published hardware-feasibility.json
  sidecar binds the run ID, training review, approval digest and original zero-step
  checkpoint manifest. The checkpoint/receipt schema and training implementation
  remain unchanged. Profile reads validate the snapshot revisions, run approval
  and initial checkpoint; they do not substitute current hardware for history.
- Saved trial dialogs expose the profile after initialization and continuation.
  Older trials without a profile show explicit absence, with no inferred hardware
  values. Interrupted profile publication is distinguished as another possible
  absence reason. If profile publication fails after initialization, the app
  reports the run ID and retains its private checkpoint for recovery; it never
  deletes training artifacts or claims that profile publication succeeded.
- Native local verification: rebuilt and ran macOS ALMG on Apple M4 Max with the
  existing Unigram stream fixture. Explicitly approved new run 1a7a4a8e9eca49299a0a978fb63c3665,
  opened its hardware profile at zero and five updates, restarted both app and
  fixture backend, reopened the paused trial/profile, resumed to ten updates and
  reopened the profile again. Every captured profile was exactly equal, with
  revision 5f5c7ea4a3638b741318afa24ace0ecff2039f53bec7567fc8fd030d35b931dd and original checkpoint
  step-000000-9b938d8971bc485e860533db2bbf2e63. An older completed trial showed
  the explicit no-profile message. All 203 pre-existing fixture file hashes
  remained unchanged. No historical records were rewritten or migrated.
- Verification: 547 Python tests passed with actual Metal and warnings as errors;
  49 Flutter tests passed; analysis and diff checks clean. New tests cover saved
  approval/execution snapshots, consent, continuation/restart identity, tamper
  rejection, legacy absence, publication failure preserving initialized checkpoints,
  and opening the saved-profile dialog. Evidence:
  /tmp/almg-stream-hardware-profile-native-qa/verification.json and native/test logs.
- Remaining: measured streamed-training calibration and duration prediction,
  broader/full-epoch feasibility and per-continuation admission integration,
  supported-recipe CPU fallback verification, and Windows/CUDA verification on
  suitable hardware. Unchanged hardware/user-action blockers remain open and
  skipped. No generated artifacts, private data, weights or unrelated edits
  are included in this commit.

P3-LMF-05 partial progress · trial-specific feasibility on every streamed continuation · 2026-11-20:
- [ ] P3-LMF-05 remains open. HTTP requests for the next five streamed training
  updates now revalidate the exact training review and live model-specific memory,
  disk, Metal working-set and runtime requirements before calling the existing
  training engine. The same gate covers legacy trials without saved hardware
  profiles. An insufficient-resource or unsupported-hardware result retains the
  previous checkpoint and allows retry after conditions improve. Continuation
  still requires explicit confirmation; stale/replayed and completed-run requests
  remain no-ops before another admission or optimizer call.
- The gate uses the engine's existing reentrant lock to keep review/continuation
  sequencing consistent. Existing checkpoint formats, receipts and training
  implementation hashes remain unchanged. The UI explains that every continuation
  rechecks trial reserves and preserves the last checkpoint on rejection.
- Native local verification: rebuilt macOS ALMG on Apple M4 Max and approved new
  Unigram trial 2ecc319c916e48059d5c5887c4f7d21f. A local QA backend fixture reported one
  byte of available memory without changing actual system memory. The app blocked
  the first continuation, displayed the retained-checkpoint reason and kept exact
  zero-step state and initialized artifact hashes. Restoring normal observations
  allowed retry to five updates. The same fixture blocked an older paused trial
  at ten updates with exact state equality. After app/backend restart, the new
  five-step checkpoint reopened unchanged and resumed to ten updates. All
  214 pre-existing fixture file hashes remained unchanged.
- Verification: 549 Python tests passed with real Metal and warnings as errors;
  49 Flutter tests passed; analysis and diff checks clean. New tests verify
  rejection before the optimizer, unchanged files/state, successful retry, replay
  idempotence, consent, legacy gating and unsupported Metal rejection; the widget
  test verifies error display, unchanged progress and retry. Evidence:
  /tmp/almg-stream-continuation-native-qa/verification.json and native/test/build logs.
- Remaining: measured streamed-training calibration and duration prediction,
  broader/full-epoch feasibility, persisted per-continuation resource observations,
  supported-recipe CPU fallback verification, and Windows/CUDA host verification.
  Unchanged hardware/user-action blockers remain open and skipped. No generated
  artifacts, private data, weights or unrelated edits are committed.

P3-LMF-05 partial progress · measured isolated streamed chunks and limited work estimate · 2026-11-20:
- [ ] P3-LMF-05 remains open. Each explicitly requested five-update streamed
  continuation now runs in a fresh local Python/Metal process. Parent and worker
  check trial-specific admission, and saved observations bind before/after state
  revisions, approval/review, resulting checkpoint manifest, both admission
  snapshots and measurement implementation. Original training/checkpoint formats
  and hashes are unchanged; existing trials remain readable and resumable.
- Measurements distinguish worker elapsed work from broader request work, which
  includes parent admission and worker startup but excludes lock queue and metric
  publication. Metal allocator peak excludes cache; process peak RSS includes
  interpreter/imports, CPU loading/source validation and checkpoint saving. Their
  unified-memory usage may overlap, so no combined measured CPU/GPU peak is claimed.
  The final chunk explicitly records that it includes held-out evaluation.
- Saved trial dialogs expose immutable continuation observations and a limited
  remaining update/checkpoint estimate: largest observed same-run nonfinal request
  work multiplied by remaining five-update chunks. It excludes final held-out
  evaluation and manual pauses; hardware/load changes can invalidate comparison.
  No full-epoch or full-training duration is claimed. Legacy trials with no
  measurements display no inferred estimate. Replays do not run another worker.
- Worker errors/timeouts tell users to inspect the last saved checkpoint. If
  measurement publication fails after a successful training chunk, the app names
  the advanced progress and retains the checkpoint; replaying the old request
  returns saved progress rather than applying duplicate updates.
- Native verification: rebuilt macOS ALMG on Apple M4 Max with the existing
  Unigram fixture. Run 8fa76c716bd244b49fe8b59ee05cdfa6 completed twenty updates through
  four distinct worker PIDs. First-chunk measurements recorded Metal peak
  187152 bytes, peak RSS 70205440 bytes, worker work
  0.0942474160110578 seconds and request work 0.3491889579454437 seconds;
  the UI showed the resulting three-chunk remaining-work estimate. App/backend
  restart recovered the first checkpoint and measurement record exactly. Continued
  through 10/15/20 updates and opened all four saved measurements; the final chunk
  flagged held-out evaluation, covering 298 validation and
  273 test windows. Release remained unapproved. An older trial showed no
  measurements/estimate. All 225 pre-existing fixture file hashes stayed unchanged.
- Verification: 551 Python tests passed with actual Metal and warnings as errors;
  both final focused measurement tests passed; 49 Flutter tests passed; analysis
  and diff checks clean. Tests cover isolated peaks, duration scope, checkpoint
  bindings, tamper rejection, consent, replay and worker/publication recovery.
  Evidence: /tmp/almg-stream-chunk-measurements-native-qa/verification.json,
  native-finish.log, recovery.log and test/build logs.
- Remaining: feed compatible streamed measurements back into subsequent admission
  estimates, estimate final evaluation/full-trial and broader/full-epoch duration,
  supported-recipe CPU fallback verification and Windows/CUDA host verification.
  Unchanged hardware/user-action blockers remain open and skipped. No private or
  generated artifacts, weights or unrelated user edits are committed.

P3-LMF-05 partial progress · compatible streamed measurements raise admission reserves · 2026-11-20:
- [ ] P3-LMF-05 remains open. Streamed-training feasibility now incorporates
  validated isolated chunk observations from matching saved trials. Compatibility
  requires the exact training review/window/source/settings, Metal hardware/MLX
  runtime, measurement producer and admission implementation. All matching trial
  directories are considered, independent of the UI history limit, including
  measured final-evaluation chunks. Historical incompatible observations remain
  readable but do not calibrate new execution.
- Calculated values remain separate from measured calibration. GPU admission
  uses at least the larger calculated/observed peak; memory and checkpoint disk
  reserves can only rise. CPU RSS plus GPU peak plus the base reserve deliberately
  overcounts possible unified-memory overlap, which the UI/report discloses.
  A bounded summary retains compatible evidence count/digest and peak-source
  run/checkpoint revisions. Changed evidence invalidates stale initial approval;
  continuation and worker admission also use the current calibrated reserves.
- Feasibility v2 snapshots preserve calibration in the existing hardware-profile
  record. Readers accept both v1 and v2 without rewriting old records. Read-only
  calibration validates historical checkpoints; it creates no new trial or
  optimizer and does not claim a full-epoch or duration guarantee.
- Native local verification: rebuilt macOS ALMG on Apple M4 Max. A fresh measured
  baseline chunk raised GPU working budget from 59392 to
  187152 bytes and memory reserve from
  268959744 to 343071504 bytes, using measured RSS
  74448896 bytes. A QA fixture reported
  306015624 available bytes, between the original and calibrated memory
  requirements, without changing actual system RAM. The app blocked approval,
  showed measured calibration and created no trial. Restoring normal observations
  allowed explicit approval of run 5b282ffd44cd4c22a0b6d4339721042d, whose saved v2
  feasibility snapshot included that evidence. Continued five updates using it.
  An older v1 profile reopened with exact equality. After app/backend restart,
  the v2 profile reopened unchanged, the new trial resumed to ten updates with
  two compatible chunks in execution admission, and a fresh review recovered
  three matching chunks. All 246 pre-existing fixture file hashes stayed unchanged.
- Verification: 553 Python tests passed with actual Metal and warnings as errors;
  49 Flutter tests passed; analysis and diff checks clean. New tests cover read-only
  calibration, measured-reserve rejection, stale approval and hardware/runtime/
  producer incompatibility while retaining historical readability. Evidence:
  /tmp/almg-stream-calibration-native-qa/verification.json and native/test/build logs.
- Remaining: final-evaluation/full-trial and broader/full-epoch duration prediction,
  broader training feasibility, supported-recipe CPU fallback verification and
  Windows/CUDA host verification. Unchanged hardware/user-action blockers stay
  open and skipped. No generated/private artifacts, weights or unrelated edits
  are committed.

P3-LMF-05 partial progress · stage-specific bounded trial work estimate including evaluation · 2026-11-20:
- [ ] P3-LMF-05 remains open. Compatible measured streamed-trial request times
  now form separate maxima for the 5/10/15/20-update stages. The final stage
  includes complete held-out evaluation, so it is not extrapolated from a normal
  training chunk. A complete twenty-update work estimate is available only when
  compatible observations cover all four stages; missing/invalid timings leave
  it unavailable. Calculated duration remains explicitly an estimate.
- Approval displays that bounded work estimate, and continuation history can use
  the saved admission-stage model plus measured current-run timings to estimate
  remaining stages, including final evaluation. The estimate includes admission,
  worker startup, updates and checkpoint IO; excludes initial model initialization,
  lock queue, measurement publication and manual pauses. It is not a wall-clock
  deadline or full-epoch forecast, and hardware/load/history changes can invalidate
  it. Stage maxima use measurements rather than earlier predicted durations.
- Feasibility v3 retains the duration model with saved approval/execution snapshots.
  Readers continue to accept v1/v2 history without rewriting records. Existing
  checkpoint/receipt formats and original training implementation hashes remain
  unchanged; evidence/code compatibility and stale-approval checks remain active.
- Native verification: rebuilt macOS ALMG on Apple M4 Max, observed no complete
  estimate before compatible final-stage data, then completed twenty updates in
  measured baseline 40321cf2422248d7b3b6128da3c0eb92. Its four stage costs
  produced 2.010453831986524 seconds of bounded request work including final
  evaluation, visibly shown before approving new run 2651570e0c3c44f2b86721d282477390.
  At five updates the new run showed remaining work from the 10/15/20 stages.
  An older v2 profile reopened unchanged. After app/backend restart, saved
  measurements and the v3 profile reopened with exact equality; resumed to ten
  updates and verified a remaining-work estimate of
  1.0955124989850447 seconds from the 15/20 stages, including evaluation.
  All 268 pre-existing fixture file hashes remained unchanged.
- Verification: 556 Python tests passed with actual Metal and warnings as errors;
  49 Flutter tests passed; analysis and diff checks clean. Added tests cover
  per-stage maxima, final-evaluation inclusion, missing/invalid evidence, completed
  work, borrowing saved admission stages and a real measured trial feeding a new
  approval estimate. Widget tests verify both displayed estimates. Evidence:
  /tmp/almg-stream-duration-native-qa/verification.json and native/test/build logs.
- Remaining: broader training/full-epoch feasibility and duration forecasting,
  supported-recipe CPU fallback verification and Windows/CUDA host verification.
  The bounded manual recipe does not establish general training capacity.
  Unchanged hardware/user-action blockers stay open and skipped. No generated
  artifacts, private data, weights or unrelated edits are committed.

P3-LMF-05 partial progress · explicit CPU classifier feasibility and saved evidence · 2026-11-20:
- [ ] P3-LMF-05 remains open. The existing classifier approval screen now shows
  a CPU-specific resource report before training. It requires no Metal/CUDA probe
  or accelerator and distinguishes classifier fitting from optional Qwen repair
  planning. Estimates cover encoded prepared rows, sparse TF-IDF with at most
  30,000 features per candidate, a 32-copy coefficient/solver-history allowance,
  memory and additional disk reserves. They are calculated, not measured peak
  memory, and provide no CPU training-duration or exhaustion guarantee.
- The UI hides approval when resources cannot be verified or are insufficient.
  The start route validates a supplied report's exact dataset, labels, settings
  and implementation and rechecks resources; legacy API clients still receive
  fresh CPU admission. Execution rechecks again before fitting, including after
  idle waits. The reproducibility record retains the exact user-approved report,
  fresh queue admission and execution snapshots. Snapshot revisions bind the job
  and original prepared-dataset approval, correctly distinct from post-split rows.
  Legacy records without optional CPU profiles remain readable. The original
  shared run-manifest module and decoder training/checkpoint formats are unchanged.
- Native verification: rebuilt macOS ALMG and used an isolated 48-row, two-label
  CPU fixture. Opened the resource report, cancelled with unchanged fixture files,
  reopened and explicitly approved CPU training with idle waiting and repair off.
  Report estimated 283831424 bytes memory and
  97846848 bytes additional disk, with accelerator_required=false.
  Candidate dddddddddddddddddddddddddddddddd completed on CPU with validation/test macro-F1
  1.0/1.0 on this contrived fixture, not a general quality claim. Opened the actual
  run reproducibility record and verified exact approval plus fresh admission and
  execution profiles. After app/backend restart the complete manifest reopened
  with exact equality; 4 candidate files and 5 earlier CPU fixture files
  retained their SHA-256 hashes. Other datasets, weights and user changes were
  outside the isolated fixture root; no external collection or repair was invoked.
- Verification: 558 Python tests passed with actual Metal regressions enabled
  and warnings as errors; 50 Flutter tests passed; analysis and diff checks clean.
  New tests cover read-only CPU-only reports, stale/low-memory rejection,
  preapproval versus post-split bindings, snapshot tamper detection, legacy
  metadata and blocked approval UI. Evidence:
  /tmp/almg-classifier-feasibility-native-qa/verification.json, native-final.log,
  recovery.log and final test/build logs.
- Remaining: other supported CPU recipe feasibility, measured classifier resource
  calibration/duration, broader neural/full-epoch feasibility and Windows/CUDA
  host verification. Unchanged hardware/user-action blockers remain open and
  skipped. No generated/private artifacts, weights or unrelated edits committed.

P3-LMF-05 partial progress · CPU image recipe feasibility and retained evidence · 2026-11-20:
- [ ] P3-LMF-05 remains open. Experimental image fitting now has a CPU-specific
  feasibility review before approval, with fresh admission and execution checks.
  The local 48x48 shape recipe estimates mask/palette layout and fitting copies;
  the caption-ridge branch estimates dense pixel targets/coefficients and the
  quadratic training Gram matrix. Both include encoded dataset, memory and disk
  budgets and explicitly require no Metal/CUDA accelerator. These are calculated
  budgets, not measured peaks, diffusion capability or a duration guarantee.
- The image dialog has its own approval action and report label. Resource/stale
  rejection cannot initialize through the new gate; legacy API clients still get
  fresh admission. Candidate reproducibility records retain the exact approved,
  queue-admission and execution reports, validated against the prepared dataset
  approval. Optional image profiles do not rewrite legacy classifier/image records.
  Shared run-manifest and decoder implementation/checkpoint modules are unchanged.
  External Commons collection remains separately permission-controlled.
- Native local verification: rebuilt macOS ALMG and used the isolated 45-example
  rendered-shape fixture. Opened the image feasibility report, cancelled with no
  fixture file changes, reopened and explicitly approved CPU image fitting with
  idle waiting off. The report calculated 20751 model scalars,
  166008 float64 layout bytes, 272314648 bytes memory reserve and
  69048700 bytes additional disk reserve. Candidate eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
  completed on CPU with held-out pixel accuracy 1.0 on this primitive local
  fixture, not a general image-quality claim. The app's reproducibility dialog
  showed exact approval plus fresh admission/execution snapshots. After app/backend
  restart the complete manifest reopened with exact equality. 12 image/earlier CPU
  artifact hash checks remained unchanged. No external collection/download ran.
- Verification: 560 Python tests passed with actual Metal regressions and warnings
  as errors; 51 Flutter tests passed; analysis and diff checks clean. New tests cover
  read-only shape estimates, stale/low-resource rejection, snapshot tampering,
  caption-ridge Gram/target dimensions using local fixtures, and distinct image
  approval UI. Caption-ridge resource math is unit-verified; this native run used
  rendered shapes and does not claim live Commons pipeline verification. Evidence:
  /tmp/almg-image-feasibility-native-qa/verification.json and native/test/build logs.
- Remaining: native caption-ridge fixture coverage, measured CPU classifier/image
  calibration and duration, broader neural/full-epoch feasibility, and Windows/CUDA
  host verification. Unchanged hardware/user-action blockers remain open and skipped.
  No generated/private artifacts, weights or unrelated edits are committed.

P3-LMF-05 partial progress · prepared-image validation before feasibility and native caption coverage · 2026-11-20:
- [ ] P3-LMF-05 remains open. Image feasibility now invokes the existing prepared
  dataset contract before calculating resource budgets. Caption inputs must be
  bounded 48x48 RGB PNGs with training/held-out splits; shape inputs must retain
  required shape/position and color coverage. Invalid bytes, dimensions/modes or
  missing coverage reject before approval rather than reaching a trainer after
  a misleading resource-fit report. Pillow oversized-header warnings/errors are
  normalized to the same actionable prepared-image error, without full allocation.
  Shared recipe validation and stored model/checkpoint formats remain unchanged.
- Native verification: rebuilt macOS ALMG with isolated generated local PNGs and
  external image reads explicitly disabled. The app rejected a 49x48 prepared
  caption fixture before approval; no candidate was created and its prepared
  dataset file remained unchanged. A separate valid 15-image fixture (12 training,
  3 held-out) exercised the caption-ridge CPU path without collection/downloads.
  Opened the feasibility report, cancelled, reopened and explicitly approved CPU
  image fitting with idle waiting off. Report calculated a
  1152-byte Gram layout, 117504 model scalars,
  940032 float64 layout bytes and 274919440 bytes memory reserve.
  Candidate bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb completed with held-out pixel similarity
  0.901801924473493 on this contrived local fixture, not a semantic image-quality claim.
  The actual run reproducibility dialog retained the exact approved report and
  fresh admission/execution snapshots. After app/backend restart, its full manifest
  reopened with exact equality; all 15 caption and previous CPU/image artifact hash
  checks matched. This verifies the prepared caption algorithm locally, not live
  Commons discovery, permissions or download behavior; those controls are unchanged.
- Verification: 561 Python tests passed with actual Metal regressions and warnings
  as errors; 51 Flutter tests passed; analysis and diff checks clean. Tests cover
  valid encoded caption fixtures plus wrong dimensions, grayscale, malformed
  base64, an oversized header and missing local-shape training coverage, with no
  preflight artifact writes. Evidence:
  /tmp/almg-caption-preflight-native-qa/verification.json, native-verified.log,
  invalid-caption-ui.txt, recovery.log and final test/build logs.
- Remaining: measured CPU classifier/image calibration and duration, broader
  neural/full-epoch feasibility and Windows/CUDA host verification. Unchanged
  hardware/user-action blockers remain open and skipped. No generated/private
  artifacts, weights or unrelated edits are included in the commit.

P3-LMF-05 partial progress · discarded CPU classifier resource trials · 2026-11-20:
- [ ] P3-LMF-05 remains open. The CPU classifier feasibility dialog now offers a
  separately confirmed discarded fit of the reviewed prepared dataset, without
  Qwen repair or idle scheduling. A fresh isolated process records fit/validation
  time and process peak RSS, then discards fitted weights. Main training and
  release remain unapproved. Fresh feasibility admission and dataset digest checks
  bind the measurement to the reviewed input; failures/timeouts save no report.
- Immutable versioned JSON history retains admission, settings, runtime, source
  digest and implementation provenance. The app can reopen the saved history.
  Measured RSS includes interpreter/imports and workspace; timed work excludes
  interpreter/import startup, idle waits, repair and main candidate persistence.
  These observations do not yet calibrate CPU estimates or predict future runs.
- Verification: rebuilt and ran the native macOS app against an isolated local
  48-row fruit/astronomy fixture. Cancel ran nothing; separate confirmation ran
  the discarded CPU comparison and displayed 0.024029791937209666 seconds and
  196165632 bytes peak RSS from worker PID 41457. History reopened exactly after
  backend/app restart. The main job stayed dataset_ready without training
  approval, both original prepared files retained their hashes, and no model
  artifacts were created. Evidence: /tmp/almg-classifier-resource-trial-native-qa/
  verification.json and native UI record captures (local evidence, not committed).
- Validation: 563 Python tests with warnings treated as errors and Metal enabled,
  52 Flutter tests, clean Flutter analysis; the final timestamp/history change
  also passed both focused resource-trial tests. Tests cover real isolated fitting,
  discarded weights, preserved input, tampered history, consent, failure and timeout.
- Remaining: compatible CPU measurement calibration and duration estimates,
  measured CPU image trials, broader neural/full-epoch feasibility, and suitable
  Windows/CUDA hardware verification. Existing hardware blockers remain open and
  skipped; P3-LMF-01 is already complete for its recorded architecture scope.

P3-LMF-05 partial progress · compatible CPU trial measurements update feasibility · 2026-11-20:
- [ ] P3-LMF-05 remains open. The next CPU classifier feasibility review now
  incorporates saved discarded-fit observations only when dataset, settings,
  labels, runtime, CPU topology and implementation match. The memory reserve is
  the greater of the calculated floor and the highest compatible process peak
  RSS with 25% headroom. Measured fit/validation time is displayed separately;
  calculated disk and total-duration fields are not relabeled as measurements.
- Calibration retains exact trial IDs and observations in the feasibility record
  and therefore in existing approval/admission/execution snapshots. A changed
  calibration requires reopening the review before approving training. Older or
  incompatible trials remain in history but do not calibrate current admission.
- Local native verification: rebuilt and ran ALMG with an isolated local 48-row
  classifier fixture; the initial report had no calibration. Separately confirmed
  discarded trial 0b0851df13e943549d9b90558afaa8f6 measured 0.026368999970145524
  seconds and 196083712 bytes peak process RSS. Reopening feasibility displayed
  these exact observations. The calculated 283831424-byte reserve remained larger
  than the measured peak plus headroom, so was preserved. After restarting app
  and backend, calibration reopened exactly; main training remained unapproved,
  both prepared files and all three prior trial-fixture files retained their
  hashes, and no fitted model artifacts were created. Local evidence is in
  /tmp/almg-cpu-calibration-native-qa/verification.json and native UI captures;
  generated evidence is not committed.
- Validation: 564 Python tests passed with warnings as errors and Metal enabled;
  52 Flutter suite tests passed and all four focused feasibility-dialog tests
  passed after adding the measured-label assertion; Flutter analysis was clean.
  Coverage includes increased admission reserves, insufficient-memory blocking,
  stale approval rejection, and incompatible runtime/data/settings/producer/CPU
  topology exclusion, using real isolated fitting with local fixtures.
- Remaining: CPU total-training duration forecasting, measured CPU image trials,
  broader neural/full-epoch feasibility and suitable Windows/CUDA verification.
  Unchanged hardware/user-action blockers remain open and skipped.

P3-LMF-05 partial progress · bounded CPU fit-work duration estimate · 2026-11-20:
- [ ] P3-LMF-05 remains open. CPU classifier feasibility now estimates fresh
  fit/validation work from the highest compatible discarded-trial time plus
  explicit 25% heuristic headroom. The versioned report includes measured range,
  sample count, exact source trial IDs, method, scope and exclusions. Without
  compatible observations, the estimate stays unavailable. Total training time
  remains unknown; startup, idle/power waits, Qwen repair, checkpoint/model saving
  and export are excluded. This is not an upper bound, confidence interval,
  checkpoint-resume estimate or extrapolation to other datasets/recipes.
- Native verification: rebuilt and ran ALMG with an isolated local 48-row
  fruit/astronomy fixture. Initial review showed no fit-work estimate. Two
  separately confirmed discarded trials measured 0.03619020897895098 and
  0.020518208970315754 seconds. Reopened feasibility displayed the calculated
  0.04523776122368872-second estimate with both source trials and exclusions.
  Explicitly approved main CPU training then completed; approval, admission and
  execution snapshots retained that exact forecast in the run manifest. The
  contrived fixture achieved validation/test macro-F1 1.0/1.0, without implying
  general model quality. After app/backend restart the manifest reopened exactly;
  all six prior fixture files and seven new candidate files retained their hashes.
  Local evidence: /tmp/almg-cpu-duration-native-qa/verification.json and native UI
  captures (generated artifacts remain outside Git).
- Validation: 565 Python tests passed with warnings treated as errors and Metal
  enabled, 54 Flutter tests passed, and Flutter analysis was clean. Coverage
  includes absent/incompatible history, real isolated multi-trial observations,
  forecast provenance and uncertainty, and visible excluded-work labels.
- Remaining: total wall-time forecasting including scheduling/persistence, measured
  CPU image trials, broader neural/full-epoch feasibility and suitable Windows/
  CUDA verification. Unchanged hardware/user-action blockers remain open and
  skipped; this bounded estimate does not close the entire requirement.

P3-LMF-05 partial progress · discarded CPU image resource trials · 2026-11-20:
- [ ] P3-LMF-05 remains open. The existing experimental CPU image feasibility
  dialog now offers separately confirmed discarded fits for local shapes and
  prepared 48x48 caption-to-pixel ridge data. Each runs in a fresh isolated CPU
  process through the existing dataset/execution contracts, without collection,
  Qwen repair, idle scheduling or model persistence. Main training/release remain
  unapproved. Fresh admission and before/after prepared-data digest checks bind
  timing and peak process RSS to the reviewed input/settings/variant.
- Immutable versioned JSON history retains source digest, variant, admission,
  runtime and implementation provenance; the native app can reopen it. Process
  peak RSS includes interpreter/imports and workspace. Fit/validation time excludes
  interpreter/import startup, scheduling waits and main candidate persistence.
  Consent rejection, failed workers and timeouts save no successful report.
  These image observations do not yet calibrate estimates or forecast duration.
- Verification: rebuilt and ran the native macOS app against isolated fixtures:
  45 local shape examples and 15 locally generated captioned PNGs (external reads
  explicitly disabled). Cancel ran nothing for each recipe. Separate confirmation
  measured shape fitting at 0.01779999991413206 seconds / 39862272 bytes peak RSS,
  and caption ridge at 0.03267183294519782 seconds / 51167232 bytes. Both saved
  histories reopened exactly after backend/app restart. Both main jobs remained
  dataset_ready without training approval; all four prepared files and seventeen
  prior fixture/artifact files retained their hashes. The trial root contained
  JSON evidence/input only, with no fitted weights. Local evidence is under
  /tmp/almg-image-resource-trial-native-qa/verification.json and native UI captures;
  generated artifacts are not committed.
- Validation: 567 Python tests passed with warnings as errors and Metal enabled;
  55 Flutter tests passed and analysis was clean. Tests exercise both actual
  isolated image variants, preserved inputs, discarded weights, history integrity,
  separate consent, stale reviews, worker failure and timeout behavior.
- Remaining: compatible image measurement calibration and bounded duration
  estimation, total wall-time forecasting, broader neural/full-epoch feasibility,
  and suitable Windows/CUDA hardware verification. Unchanged hardware/user-action
  blockers remain open and skipped.

P3-LMF-05 partial progress · measured CPU image calibration and bounded fit estimate · 2026-11-20:
- [ ] P3-LMF-05 remains open. Saved discarded image trials now calibrate the next
  CPU image feasibility review only when prepared data, settings, mode/variant,
  runtime, CPU topology and implementation match. Admission takes the greater of
  the calculated memory floor and highest compatible process peak RSS plus 25%
  headroom; incompatible evidence cannot lower or replace calculated reserves.
  Newly observed calibration requires a fresh review before training approval.
- The same report supplies a bounded fit/validation work estimate using highest
  compatible measured time plus explicit 25% heuristic headroom, retaining sample
  count, observed range, source trial IDs, method and exclusions. It is not an
  upper bound or total wall-time prediction. Startup/imports, idle/power waits,
  Qwen repair, checkpoint/model saving and export remain excluded. Existing saved
  image hardware profiles without the optional calibration fields remain readable.
- Native verification: rebuilt and ran ALMG against 45 local shape examples and
  15 locally generated captioned PNGs with external reads disabled. Each initial
  review had no calibration; a separately approved discarded trial populated the
  reopened report. Shapes measured 0.01902041700668633 seconds and 39944192 bytes
  peak process RSS, estimating 0.023775521258357912 seconds of fit work. Caption
  ridge measured 0.032490332960151136 seconds and 49922048 bytes, estimating
  0.04061291620018892 seconds. Both retained the larger calculated memory floors
  (272314648 and 274919440 bytes respectively).
- Explicitly approved both main CPU runs in the app. Shape held-out pixel accuracy
  was 1.0 and caption pixel similarity 0.901801924473493 on these local fixtures;
  this is not evidence of general image-generation quality. Approval, admission
  and execution snapshots retained the exact reviewed calibration/estimate. Both
  run manifests reopened exactly after app/backend restart; all 23 prior fixture/
  artifact files and 10 new candidate files retained their hashes. Local evidence:
  /tmp/almg-image-calibration-native-qa/verification.json and native UI captures;
  generated evidence and weights stay outside Git.
- Validation: 569 Python tests passed with warnings as errors and Metal enabled,
  55 Flutter tests passed, and analysis was clean. Coverage includes both actual
  isolated image variants, stale approval rejection, insufficient-memory blocking,
  incompatible mode/variant/runtime/data/settings/producer/CPU exclusion, invalid
  timing, and legacy profile readability.
- Remaining: total wall-time forecasting including scheduling/persistence, broader
  neural/full-epoch feasibility and suitable Windows/CUDA verification. Unchanged
  hardware/user-action blockers remain open and skipped.

P3-LMF-05 partial progress · bounded planned-decoder diagnostic time estimate · 2026-11-20:
- [ ] P3-LMF-05 remains open. Planned-model backward feasibility now estimates
  the same bounded synthetic diagnostic workflow from compatible isolated v4
  measurements: highest observed complete child-workflow time plus explicit 25%
  heuristic headroom. The record retains source report IDs/revisions, measured
  times/range, sample count, method, scope and exclusions; the app distinguishes
  these observations from the calculated estimate. Full-training duration stays
  unknown, and no optimizer-throughput extrapolation is made.
- Existing exact initialization, hardware/runtime, producer, precision, isolated
  process and integrity compatibility checks also gate timing evidence. Missing,
  nonpositive or invalid workflow times produce no time estimate while preserving
  valid peak-memory calibration. Timing includes model loading, feasibility and
  CPU numerical checks, and excludes interpreter/import startup, approval waits,
  parent report publication and full dataset training. Headroom is a heuristic,
  not a confidence interval or guaranteed upper bound.
- Native verification: rebuilt and ran ALMG with an isolated copy of the existing
  8704-parameter two-layer initialization. Initial review showed no estimate.
  Explicitly confirmed the five-step Metal diagnostic and observed
  0.2564115000423044 seconds of isolated workflow work. Reopened feasibility showed
  0.3205143750528805 seconds based on saved report
  2502eed125e74ca0a62433c20785100e. Updated weights were discarded and main training/
  release remained unapproved. After app/backend restart the saved diagnostic
  reopened exactly and the next review reconstructed the identical estimate.
  All three copied plan/initialization files and three original artifact files
  retained their hashes. Local evidence: /tmp/almg-architecture-duration-native-qa/
  verification.json and native UI captures; generated artifacts remain outside Git.
- Validation: 571 Python tests passed with warnings as errors and Metal enabled,
  55 Flutter tests passed, and analysis was clean. Tests cover multi-observation
  maximum selection/provenance, read-only review, absent/invalid/boolean timings,
  continued memory calibration and the estimate/exclusion labels in the app.
- Remaining: total training wall-time forecasting, broader neural/full-epoch
  feasibility and suitable Windows/CUDA hardware verification. Unchanged hardware/
  user-action blockers remain open and skipped.

P3-LMF-05 partial progress · feasibility before saved generated-decoder trial approval · 2026-11-20:
- [ ] P3-LMF-05 remains open. New generated-text saved decoder trials now show
  a hardware feasibility report before the app requests explicit training approval.
  The read-only review requires Apple silicon/MLX Metal and checks current memory,
  disk and Metal working-set recommendation against calculated FP32 budgets for
  the exact existing four-word, width-8 fixture (704 parameters / 2816 weight bytes).
  It includes gradients, conservative parallel-trajectory/activation buffers and
  checkpoint storage. These are calculated reserves, not peaks or duration claims.
- Fresh admission runs before trial creation and again at worker submission. The
  reviewed approval and submission admission profiles are saved in the trial
  record before its optimizer worker runs. Existing memory/disk checks still run
  before and during fitting. Public legacy requests without a reviewed report
  still receive fresh admission, labeled as not reviewed before approval. Local
  reviewed-dataset trials and resumes retain their separate existing workflow.
  Training/checkpoint/bundle schemas and source-pinned specifications are unchanged;
  the new hardware metadata is optional for older records.
- Native verification: rebuilt and ran ALMG with an isolated generated-text
  fixture. Cancelled feasibility created no trial. Explicit approval of calculated
  269547520-byte memory / 67710976-byte disk reserves completed actual Metal
  training in trial 928fcc4293f244198c3eb7f4024c59a8. Loss fell from
  1.3726524114608765 to 0.0673074871301651; checkpoint resume matched uninterrupted
  training within 8.940696716308594e-08, generated tokens matched the contrived
  fixture, and no pretrained student weights were loaded. The exact reviewed
  hardware profile survived completion and app/backend restart. All seven trial
  files and 23 prior artifact files retained their hashes. Local evidence:
  /tmp/almg-generated-feasibility-native-qa/verification.json and native UI records;
  generated weights and evidence stay outside Git.
- Validation: 574 Python tests passed with warnings as errors and Metal enabled,
  56 Flutter tests passed, and analysis was clean. Tests cover no model allocation
  during review, parameter accounting, consent/stale-review/unsupported-device/
  low-memory/disk blocking before submission, profile persistence before an actual
  training worker, FP32 checkpoint equivalence and visible approval blocking.
- Remaining: dedicated preapproval profiles for reviewed local data and resumed
  trials, total wall-time estimates, broader neural/full-epoch feasibility and
  suitable Windows/CUDA hardware verification. Unchanged hardware/user-action
  blockers remain open and skipped.

P3-LMF-05 partial progress · reviewed-local-data decoder feasibility before approval · 2026-11-20:
- [ ] P3-LMF-05 remains open. New saved trials on explicitly reviewed local
  decoder datasets now receive a distinct hardware report and final approval
  dialog. The read-only report uses the validated dataset/tokenizer manifest,
  exact vocabulary size, train/validation/test window counts and stored data size.
  FP32 budgets include vocabulary-dependent parameters/logits and all training-
  window graphs retained by the existing bounded loss function. Data quality,
  contamination, tokenizer and trial-size preflight still precede admission.
- Review/admission bind the dataset ID, manifest/content hashes, tokenizer
  fingerprint and unchanged training specification. Fresh checks run before
  creating the trial and at submission; reviewed approval and admission evidence
  is retained as optional local_dataset_trial_hardware metadata before fitting.
  New public local-data requests without an explicit hardware review still get
  fresh admission and are labeled accordingly. Engine/checkpoint/bundle formats
  and source-pinned training specifications remain unchanged.
- Native verification: rebuilt and ran ALMG with six local four-word documents,
  saved dataset 072c37c8c9fe42cb9a27f15d60db921f, vocabulary four, and split window
  counts 4/1/1. Cancelled hardware review created no trial. Explicit approval of
  calculated 269555712-byte memory and 67710976-byte disk reserves completed
  trial b5ef56c1fb284cb8b36111fa84074574 with a step-50 checkpoint. Training loss
  fell from 1.365828275680542 to 0.06752631813287735; validation/test next-token
  accuracy was 1.0/1.0 on this contrived fixture, not a general quality claim.
  The exact reviewed profile survived training and app/backend restart. All three
  dataset files, seven trial/checkpoint/bundle files and 25 prior artifact files
  retained their hashes. Local evidence: /tmp/almg-local-feasibility-native-qa/
  verification.json and native UI captures; generated data/weights remain outside Git.
- Validation: 576 Python tests passed with warnings as errors and Metal enabled,
  57 Flutter tests passed, and analysis was clean. Added coverage checks read-only
  exact data/tokenizer binding, larger byte-tokenizer/window resource accounting,
  incompatible/generated-versus-local and stale dataset reviews, and actual local
  Metal training with saved pre-worker profiles and unchanged prepared files.
- Remaining: dedicated resume and automatic factory-handoff feasibility profiles,
  total wall-time estimates, broader neural/full-epoch feasibility and suitable
  Windows/CUDA verification. Unchanged hardware/user-action blockers stay open
  and skipped.

P3-LMF-05 partial progress · checkpoint-bound hardware review before saved-trial resume · 2026-11-20:
- [ ] P3-LMF-05 remains open. Saved decoder trials now require a fresh native
  feasibility review before resume approval. Read-only review requires an inactive
  interrupted trial with an unchanged training specification and no completed
  bundle. It binds the prior approval hash plus the step-50 checkpoint manifest,
  decoder and tokenizer hashes, and verifies bounded checkpoint metadata/file
  checksums without constructing model tensors. A missing checkpoint is explicitly
  represented as zero saved steps and a restart from fresh weights.
- Submission rechecks resources, feasibility implementation, checkpoint hashes
  and prior approval lineage before queuing optimization. Resume approval and
  admission reports append to optional resume_hardware_reviews; original training
  profiles and previous approvals are preserved. The existing checkpoint loader,
  execution resource checks, cancellation and idle/AC policy remain in force.
  Legacy API resume requests still get fresh admission, labeled when no explicit
  hardware review was supplied. Core training and artifact formats are unchanged.
- Native verification: rebuilt and ran ALMG against six local documents. A local
  fixture interrupted explicitly approved Metal training immediately after its
  actual step-50 checkpoint. Trial fdddb100fa83476ea2a1fb5d6fb37dec then displayed
  checkpoint-bound resume feasibility. Cancel preserved the interrupted record
  exactly. Renewed approval reused that same checkpoint and completed training;
  the original local-data hardware profile and prior approval were retained.
  Loss fell from 1.365828275680542 to 0.06752631813287735, with validation/test
  accuracy 1.0/1.0 on the contrived fixture, not a general quality claim.
- After app/backend restart the complete trial and resume profile reopened exactly.
  All three checkpoint files, three dataset files, seven completed trial files and
  27 prior artifact files retained their hashes. This fixture does not establish
  physical sleep/power recovery. Local evidence is under
  /tmp/almg-resume-feasibility-native-qa/verification.json and native UI captures;
  generated data, checkpoints and weights stay outside Git.
- Validation: 579 Python tests passed with warnings as errors and Metal enabled,
  58 Flutter tests passed, and analysis was clean. Added tests cover read-only
  zero-checkpoint review, stale/consent rejection, changed submission feasibility
  blocking the optimizer queue, actual interruption/checkpoint reuse, original
  profile preservation, corrupt checkpoint rejection and distinct resume controls.
- Remaining: automatic factory-handoff feasibility profiles, total wall-time
  estimates, broader neural/full-epoch feasibility and suitable Windows/CUDA
  verification. Unchanged hardware/user-action blockers stay open and skipped.

P3-LMF-05 partial progress · factory-handoff feasibility before decoder approval · 2026-11-20:
- [ ] P3-LMF-05 remains open. The main workbench's from-scratch factory
  confirmation now opens a dedicated hardware feasibility review before creating
  its linked saved trial. Review binds the workbench job, exact executable
  proposal ID/revision, selected generated/local-data scope and unchanged training
  specification. Fresh resources and proposal bindings are checked again at
  submission. Cancellation leaves the factory review job unchanged.
- The linked trial retains the exact reviewed report and admission as optional
  factory_hardware_review metadata before optimizer work can run, alongside its
  generated/local-data profile. Legacy API calls still get admission, explicitly
  labeled when no hardware review was supplied. Existing approach consent,
  dataset checks, idle/AC selection, trial linkage and artifact formats remain in
  force. No collection or model release is implied by this hardware approval.
- Native verification: rebuilt and ran ALMG with deterministic offline planner
  fixtures for both generated text and six reviewed local documents. For each,
  Cancel preserved the factory job and created no linked trial; renewed hardware
  approval completed actual Metal training and displayed the exact proposal-bound
  report through View linked decoder trial. Generated trial
  9e930289d8504920bfc8f02e82e186bd reduced loss from 1.3726524114608765 to
  0.0673074722290039 without loading pretrained student weights. Reviewed-data trial
  55e5ce6a53414f8fb5928bdd51aeb172 reduced loss from 1.365828275680542 to
  0.06752630323171616, with validation/test accuracy 1.0/1.0 on the contrived
  fixture, not a general quality claim. Immediate execution was selected through
  the app's idle/AC control; physical idle/power verification remains separate.
- After app/backend restart, both workbench links, saved trials and hardware
  profiles reopened exactly. All three prepared dataset files, 21 new artifact/
  job/proposal files and 33 prior artifact files retained their hashes. Local
  evidence: /tmp/almg-factory-feasibility-native-qa/verification.json and native UI
  captures; generated fixtures, checkpoints and weights remain outside Git.
- Validation: 580 Python tests passed with warnings as errors and Metal enabled,
  59 Flutter tests passed, and analysis was clean. Coverage includes read-only
  factory review, stale approach/hardware rejection, report retention before worker
  submission, durable linkage, unavailable approaches and accurate legacy-review
  provenance, with a distinct final factory approval control.
- Remaining: total training wall-time estimates, broader neural/full-epoch
  feasibility and suitable Windows/CUDA verification. Unchanged hardware/user-
  action blockers remain open and skipped.

P3-LMF-05 partial progress · measured saved-trial worker work and compatible estimate · 2026-11-20:
- [ ] P3-LMF-05 remains open. Saved decoder workers now append optional versioned
  elapsed-work observations without changing the training/checkpoint engine.
  Timing wraps actual model loading, training, evaluation, checkpoint/bundle
  persistence and engine state writes, and excludes queue/approval/idle waits,
  the instrumentation hardware probe and observation publication. This is shared-
  backend worker timing, not isolated peak-memory evidence or total wall time.
  Evidence capture/publication failure preserves the engine result and artifacts.
- Feasibility can estimate the same worker work from compatible completed
  observations, using the highest time plus explicit 25% heuristic headroom.
  Reports retain source trial/measurement IDs and revisions, observed range,
  count, method and exclusions. Compatibility requires exact specification/data,
  runtime/CPU topology/Metal device, implementation and input-checkpoint hashes;
  interrupted, corrupt or mismatched observations are excluded. Fresh work and
  step-50 resume work are distinct. History considers the latest 200 trial records.
  Total wall-clock duration remains unknown; the estimate is not an upper bound.
- Native verification: rebuilt and ran ALMG with an isolated generated-text trial
  53ff5b9bb38643b19b8ab7dcebd1fd8f. The initial review had no estimate. Explicitly
  approved real Metal training completed and saved a measured worker duration of
  1.3783700410276651 seconds. The next review displayed a calculated
  1.7229625512845814-second worker-work estimate based on that exact observation.
  Cancelling created no second trial and did not change the trained files.
  After app/backend restart, both the observation and reconstructed estimate
  reopened exactly. All seven trial/checkpoint/bundle files and 45 prior artifact
  files retained their hashes. Local evidence is under
  /tmp/almg-worker-duration-native-qa/verification.json and native UI captures;
  generated fixtures, checkpoints and weights remain outside Git.
- Validation: 582 Python tests passed with warnings as errors and Metal enabled,
  60 Flutter tests passed, and analysis was clean. Coverage includes real complete
  worker timing, estimate provenance, absent history, runtime/implementation/
  checkpoint/approval/outcome/timing-integrity exclusions, no fresh-work forecast
  for a different checkpoint, and optional-publication failure preserving the
  engine's result and completed state. Existing real local-data/resume tests also
  execute the timing wrapper while preserving original checkpoints and profiles.
- Remaining: queue/idle/approval-aware total wall-time estimates, broader neural/
  full-epoch feasibility and suitable Windows/CUDA hardware verification.
  Unchanged hardware/user-action blockers remain open and skipped.

P3-LMF-06 partial progress · versioned SGD/AdamW checkpointed optimizer fixture · 2026-11-20:
- [ ] P3-LMF-06 remains open. Added a separate bounded optimizer-training path for
  existing freshly initialized planned decoders, preserving all prior trial and
  artifact formats. Version-1 settings select SGD or AdamW, learning rate, warmup/
  cosine scheduling and global gradient clipping. The ten-step fixture uses FP32
  Metal causal gradients and NumPy optimizer arrays, with a 16384-parameter cap.
  AdamW first/second moments and scheduler step are durable in a new checkpoint
  format; restored execution is compared with an uninterrupted reference.
- A resource review precedes explicit Train and save approval. AdamW moment bytes
  are included in calculated CPU reserves. Source initialization/config/hash and
  implementation are bound to the review; invalid settings, stale reviews and
  unsupported resources cannot start. The fixture rejects nonfinite gradients/
  updates and failed loss/resume checks. It retains a private trained model plus
  a step-five checkpoint; the original initialization is never overwritten.
  Saved history verifies file hashes and runs the saved model's own CPU inference.
- Native verification: rebuilt and ran ALMG with the existing 8704-parameter
  two-layer initialization, copied into an isolated fixture root. Explicitly
  reviewed and trained SGD fixture c60181c25234492aa1c58eb4b91dd161 and AdamW
  fixture 4e1e83b3fb924fdc8468025bc4d3e405 at learning rate 0.01. SGD train loss
  fell 4.852477073669434 → 4.767636299133301 (synthetic validation
  4.86411190032959 → 4.830671310424805); AdamW train loss fell to
  3.6877036094665527 (validation 4.01680326461792). AdamW review accounted for
  69632 moment bytes; SGD has no moment buffers. Both restored step five and
  completed step ten with parameter and optimizer-state max error 0.0 versus the
  uninterrupted reference, including the restored scheduler counter.
- After app/backend restart both records reopened exactly and saved-model CPU
  generation reproduced their token IDs. All ten new checkpoint/model/report
  files, three source plan/initialization files and 42 prior artifact files
  retained their hashes. No pretrained student weights were loaded and no release
  was approved. Local evidence: /tmp/almg-optimizer-engine-native-qa/verification.json
  and native UI captures; generated weights/checkpoints remain outside Git.
- Validation: 586 Python tests passed with warnings as errors and Metal enabled,
  61 Flutter tests passed, and analysis was clean. Added coverage includes strict
  config/schedule/clipping bounds, NaN/missing-gradient/moment rejection, durable
  AdamW moment/counter restoration, changed/tampered checkpoint rejection, consent/
  stale-review guards, both actual Metal optimizers, private model reload and
  optimizer edits invalidating the app's previous resource review.
- Remaining: approved text-corpus/tokenizer integration, independent checkpoint
  continuation/cancellation controls, gradient accumulation, configurable sequence/
  batch/step budgets, validated mixed precision, interruption/resource monitoring
  across general training, and the profiled 50M–100M engineering target. This is a
  synthetic token-ID engineering fixture, not completed general pretraining or a
  general text-generation quality result. P3-LMF-05 stays open for broader-engine
  profiling and unavailable Windows/CUDA verification; unchanged hardware/user-
  action blockers remain skipped.

P3-LMF-06 partial progress · versioned token-weighted gradient accumulation · 2026-11-20:
- [ ] P3-LMF-06 remains open. The bounded optimizer fixture now accepts version-2
  training settings with one or two microbatches per optimizer update. Gradients
  are averaged by real target-token counts, then globally clipped once before one
  SGD/AdamW update. Scheduler counters and checkpoint steps count optimizer updates,
  not microbatches. Review accounts for an additional FP32 accumulation buffer and
  rejects two-way accumulation when the initialized effective batch has one row.
- Version-1 settings retain their original exact shape and implicitly execute one
  full-batch microbatch. Existing checkpoint/artifact wrappers remain readable;
  saved-history reads now validate the versioned config, restore optimizer/moment/
  scheduler state, verify file hashes and reproduce trained-model CPU inference.
  Changing accumulation in the app invalidates its previous resource review.
- Native verification: rebuilt and ran ALMG with the isolated 8704-parameter
  two-layer initialization. Both copied legacy v1 SGD/AdamW records and actual
  checkpoints loaded unchanged before new writes. Explicitly reviewed and trained
  two-microbatch SGD fixture 4a88f4fbc62640dca3b4eacb8afade62 and AdamW fixture
  445d84b3e26b4a999bcbdd00e2b270b6. Each used two effective rows / one row per
  microbatch, sixteen real targets per update, twenty microbatch backward calls in
  the recorded ten-update trajectory, and a calculated 34816-byte accumulation
  buffer. Initial accumulated gradients agreed with the full-batch gradient within
  1.4901161193847656e-08. SGD loss fell 4.852477073669434 → 4.767636299133301;
  AdamW loss fell to 3.6877036094665527 on the synthetic token-ID fixture.
- Both restored checkpoint step five and finished optimizer/scheduler step ten;
  final parameter and optimizer-state max errors versus uninterrupted accumulated
  execution were 0.0. After app/backend restart all four v1/v2 records, checkpoint
  restoration and saved-model CPU generation reopened exactly. All twenty optimizer
  artifact files (including ten legacy copies), three source files and 45 prior
  artifact files retained their hashes. Local evidence:
  /tmp/almg-gradient-accumulation-native-qa/verification.json and native UI captures;
  generated data, checkpoints and weights remain outside Git.
- Validation: 589 Python tests passed with warnings as errors and Metal enabled,
  61 Flutter tests passed, and analysis was clean. Coverage includes unequal
  target-count weighting, empty/mismatched/nonfinite/overflowing gradients,
  version/bounds rejection, incompatible effective-batch admission, both actual
  accumulated Metal optimizers, update cadence, checkpoint state and UI review
  invalidation. These fixture results do not establish general language quality.
- Remaining: approved text-corpus/tokenizer integration, independent continuation/
  cancellation, larger configurable sequence/batch/step budgets, validated mixed
  precision, general interruption/resource monitoring and the profiled 50M–100M
  target. P3-LMF-05 and unavailable hardware/user-action criteria stay open; unchanged
  blockers remain skipped while this engine work progresses.

P3-LMF-06 partial progress · bounded mixed FP16 training · 2026-11-20:
- [ ] P3-LMF-06 remains open. Version-3 optimizer settings explicitly select FP32
  or mixed FP16 computation and bind the fixed loss scale to review/checkpoints.
  Mixed mode uses FP16 matrix products, FP32 normalization/attention softmax/loss,
  and FP32 master weights, gradients and SGD/AdamW state. Gradients are unscaled
  before token-weighted accumulation and global clipping; nonfinite gradients
  stop the fixture. Conservative FP32 resource reserves remain in place; this
  change does not promise measured memory savings or dynamic loss scaling.
- Changing precision invalidates prior app review. Version-1/2 settings and saved
  checkpoints remain readable without rewriting existing artifacts. Mixed mode
  uses loss scale 128; unsupported modes/scales and changed checkpoint bindings
  are rejected. The existing 16384-parameter/ten-update fixture cap still applies.
- Native verification: rebuilt and ran ALMG on this Mac using the isolated local
  8704-parameter two-layer initialization and external collection disabled.
  Reopened all four copied v1/v2 optimizer records before writes. Explicitly
  reviewed and trained mixed FP16 with two microbatches per update for SGD record
  32fcf8af2973489298f7d794accf1f03 and AdamW record
  4f05c4d13b7247439d1114ef2dd90d63. SGD loss fell 4.852474212646484 →
  4.767632484436035; AdamW loss fell to 3.687514066696167. Both completed ten
  optimizer/scheduler updates and twenty recorded microbatch backward calls.
  Initial loss differed from the FP32 reference by 2.86102294921875e-06; causal
  prefix error was 0.0. Accumulated/full-batch gradient error was
  7.772445678710938e-05, below the explicit mixed-mode 0.001 tolerance.
- Both restored step-five model/optimizer/scheduler state and matched uninterrupted
  execution with 0.0 final parameter and moment errors. After app/backend restart,
  all six v1/v2/v3 records reopened exactly, including checkpoint restoration and
  trained-model CPU token generation. All thirty optimizer files, three source
  files and 65 prior artifact files retained their hashes. Evidence is retained in
  /tmp/almg-mixed-precision-native-qa/verification.json and native UI captures;
  generated data, checkpoints and weights remain outside Git.
- Validation: 591 Python tests passed with warnings as errors and Metal enabled;
  61 Flutter tests passed and analysis was clean. Tests cover precision/scale
  rejection, nonfinite and non-FP32 master gradients, actual mixed SGD/AdamW loss
  reduction, FP32 checkpoint state, causal behavior, restoration and review reset.
- Remaining: approved text-corpus/tokenizer integration, independent continuation
  and cancellation, larger configurable batch/sequence/step budgets, general
  interruption/resource monitoring and profiled 50M–100M training. Mixed precision
  is verified only for this bounded synthetic fixture, not general model quality
  or large-model training. Unchanged hardware/user-action blockers remain open
  and skipped; P3-LMF-01 is already complete for its recorded architecture scope.

P3-LMF-06 partial progress · bounded configurable batch and sequence · 2026-11-20:
- [ ] P3-LMF-06 remains open. Version-4 optimizer settings explicitly select a
  batch of one/two rows and sequence length four/eight, bounded by the initialized
  plan. Review reports selected rows, sequence length and real targets per update.
  Unsupported settings and selections beyond the plan cannot start. Two-way
  accumulation requires two selected rows. Full-plan conservative memory reserves
  remain; selecting smaller dimensions does not claim measured memory savings.
- Both app controls invalidate previous review, and selected dimensions are bound
  to approval, checkpoint configuration and saved run records. The Metal training
  path actually uses the selected tensor dimensions, with target counts recorded
  in every optimizer update. Version-1/2/3 settings preserve their original implicit
  dimensions and remain readable without rewriting old records/checkpoints.
- Native verification: rebuilt and ran ALMG on this Mac with the isolated local
  8704-parameter two-layer initialization and external collection disabled.
  Reopened all six copied v1/v2/v3 records before writes. In the app, batch one
  with two-way accumulation displayed a blocker, omitted the train action and
  created no optimizer record. Changed to one microbatch and explicitly reviewed/
  trained batch one / sequence four using mixed FP16 SGD record
  8c9f93bf34b4426bb22cc392007feeae. Loss fell 4.818500518798828 →
  4.669388771057129; each update used four real targets and one microbatch.
  Then selected batch two / sequence eight with two-way accumulation for mixed
  FP16 AdamW record a562511f287244adadc036213d06af41. Loss fell
  4.852474212646484 → 3.687514066696167; each update used sixteen targets and
  two microbatches. Both completed ten optimizer/scheduler updates, restored the
  step-five checkpoint and matched uninterrupted final weights/moments exactly.
- After app/backend restart all eight v1/v2/v3/v4 records reopened exactly,
  including checkpoint restoration and trained-model CPU generation. All forty
  optimizer files, three source files and 95 prior artifact files retained their
  hashes. Evidence: /tmp/almg-dimensions-native-qa/verification.json and native
  captures. Generated datasets, checkpoints and weights remain outside Git.
- Validation: 593 Python tests passed with warnings as errors and Metal enabled,
  61 Flutter tests passed, and analysis was clean. New tests cover strict versioned
  dimension bounds, incompatible plan/accumulation rejection before writes, actual
  FP32 and mixed FP16 execution at one row/four tokens, saved target counts, changed
  dimension approval/checkpoint rejection and both app controls resetting review.
- Remaining: approved text-corpus/tokenizer integration, independent continuation
  and cancellation, larger batch/sequence/step budgets, general interruption and
  resource monitoring, and profiled 50M–100M training. These bounded synthetic runs
  do not establish corpus quality or large-model feasibility. Unchanged hardware/
  user-action blockers stay open and skipped while independent work continues.

P3-LMF-06 partial progress · reviewed bounded optimizer update budgets · 2026-11-20:
- [ ] P3-LMF-06 remains open. Version-5 settings support ten or twenty optimizer
  updates. Earlier version-1/2/3/4 settings retain their exact ten-update contract.
  The selected budget drives warmup/cosine scheduling, complete update logs,
  optimizer/scheduler counters and checkpoint restoration. Checkpoints are saved
  at the budget midpoint (step five or ten); saved-history validation derives the
  exact expected checkpoint paths from validated settings and checks their hashes.
- The app exposes the budget and invalidates review when it changes. Preapproval
  review reports optimizer updates, checkpoint step, recorded microbatch backward
  calls and the separate uninterrupted comparison budget. The UI explains that
  verification repeats the selected budget in that comparison; recorded step logs
  cover the checkpointed trajectory. This remains a bounded synthetic fixture,
  not an arbitrary-duration training or measured time-estimation claim.
- Native verification: rebuilt and ran ALMG on this Mac with the isolated local
  8704-parameter two-layer initialization and external collection disabled.
  Reopened all eight copied v1/v2/v3/v4 records unchanged before writes. Reviewed
  the default ten-update configuration, changed to twenty and verified the prior
  train action disappeared pending renewed review. Explicitly approved/trained
  two-row/eight-token, two-microbatch FP32 SGD record
  f328cf128c9e4fe5a15a7e1f52b6630a and mixed FP16 AdamW record
  b86d0e612dbd40bf898d5805a9272bf7. SGD loss fell 4.852477073669434 →
  4.686117172241211; AdamW loss fell 4.852474212646484 → 2.6992383003234863.
  Both recorded steps one through twenty, forty microbatch backward calls and
  twenty optimizer/scheduler updates. Final scheduled learning rate was 0.001.
- Both restored model/optimizer/scheduler state from step ten and matched the
  uninterrupted twenty-update execution with 0.0 final parameter/moment errors.
  After app/backend restart, all ten v1/v2/v3/v4/v5 records reopened exactly,
  including checkpoint restoration and trained-model CPU generation. All fifty
  optimizer files, three source files and 135 prior artifact files retained their
  hashes. Evidence: /tmp/almg-budget-native-qa/verification.json and native UI
  captures; generated datasets, checkpoints and weights remain outside Git.
- Validation: 595 Python tests passed with warnings as errors and Metal enabled,
  61 Flutter tests passed, and analysis was clean. New tests cover budget bounds,
  legacy-version rejection of twenty updates, full scheduler cadence, actual FP32
  and mixed FP16 twenty-update execution, exact midpoint restoration, changed-budget
  checkpoint/approval rejection and app review invalidation.
- Remaining: approved text-corpus/tokenizer integration, independent continuation
  and cancellation, broader training budgets, general interruption/resource
  monitoring and profiled 50M–100M training. Synthetic fixture loss reductions do
  not establish general language quality. Unchanged hardware/user-action blockers
  remain open and skipped while independent work continues.

P3-LMF-06 partial progress · observed optimizer work and shared memory · 2026-11-20:
- [ ] P3-LMF-06 remains open. Bounded optimizer runs now save versioned workflow
  measurements: synchronized elapsed work, active Metal samples after every
  optimizer update, shared Metal peak counters before/after, and process-lifetime
  RSS high-water observations in bytes. Samples distinguish uninterrupted
  reference, checkpointed, resumed and finished phases. Shared counters are never
  reset. Observations are included in the saved record revision and their producer
  in the preapproval implementation fingerprint; older records remain readable.
- Calculated admission reserves stay separate and unchanged. The app presents
  observed time/sample memory and explicitly identifies shared-process scope.
  RSS/Metal peak counters can include earlier or concurrent work; active-memory
  samples exclude cached buffers and may miss transient peaks. These are not
  isolated trial peak measurements, model-only memory costs or duration forecasts.
  Timing includes source loading, initial checks, both optimizer trajectories,
  checkpoint I/O, final evaluation and CPU generation, plus sampling overhead;
  excludes admission/queue/approval waits and final report publication.
- Native verification: rebuilt and ran ALMG on this Mac with the isolated local
  8704-parameter two-layer initialization and external collection disabled.
  Reopened all ten copied older records before writes. Explicitly reviewed/trained
  twenty-update, two-microbatch FP32 SGD record efe3de36c01d4369b77da3e618c4f6cd
  and mixed FP16 AdamW record 064b57ddddfe4d52bb34bd49e0809f38. Measured workflow
  times were 0.2680305000394583 and 0.9372240829980001 seconds respectively.
  Each saved forty-one ordered phase samples: twenty reference updates, ten
  checkpointed updates, ten resumed updates and finish. Sampled active Metal
  maximum was 35152 bytes for each; shared process RSS high-water observations
  were 237617152 and 240599040 bytes. The app displayed the measured scope caveats.
- SGD loss fell 4.852477073669434 → 4.686117172241211; AdamW loss fell
  4.852474212646484 → 2.6992383003234863. Both restored step-ten model/optimizer/
  scheduler state, completed twenty updates and matched uninterrupted final
  weights/moments with 0.0 errors. After app/backend restart all twelve records,
  their observations, checkpoint restoration and trained-model CPU generation
  reopened exactly. All sixty optimizer files, three source files and 185 prior
  artifact files retained their hashes. Evidence:
  /tmp/almg-monitor-native-qa/verification.json and native UI captures; generated
  datasets, checkpoints and weights remain outside Git.
- Validation: 597 Python tests passed with warnings as errors and Metal enabled,
  62 Flutter tests passed, and analysis was clean. Coverage includes synchronized
  sample scope, no counter resets, RSS unit conversion, actual forty-one-phase
  optimizer observations, checkpoint recovery, persisted reads and UI disclosure.
- Remaining: approved text-corpus/tokenizer integration, independent continuation
  and cancellation, broader training budgets, general interruption/resource
  monitoring, isolated peak profiling/calibration for the wider engine and the
  profiled 50M–100M target. These synthetic runs do not establish corpus quality
  or large-model feasibility. Unchanged hardware/user-action blockers remain open
  and skipped while independent work continues.

P3-LMF-05 partial progress · compatible optimizer-work estimates · 2026-11-20:
- [ ] P3-LMF-05 remains open. Preapproval review for the bounded optimizer fixture
  now derives an approximate work-time estimate from verified completed compatible
  runs. Compatibility requires the exact initialization/model hash, model/training
  configuration, producer fingerprint and recorded Python/NumPy/MLX/Metal device/
  CPU topology. New reviews persist runtime context and bind it to approval. Older
  records remain readable; observations without compatible context are not reused.
- The estimate is the highest compatible measured work time plus 25% headroom,
  with source record IDs/revisions, measured range and sample count retained.
  It is explicitly labeled estimated rather than measured. Both reference and
  checkpointed trajectories, checkpoint I/O and inference checks are included;
  queue, approval/admission waits and report publication are excluded. This is a
  bounded-work heuristic, not a confidence interval, total wall-time guarantee or
  general pretraining forecast. Only the latest twenty verified records for this
  initialization are considered. Calculated memory/disk reserves are unchanged;
  shared-process memory samples never reduce admission reserves.
- Native verification: rebuilt and ran ALMG on this Mac with the isolated local
  8704-parameter two-layer initialization and external collection disabled.
  Reopened all twelve copied older records before writes. Twenty-update/two-way
  accumulation reviews initially had no compatible estimate. Explicitly approved
  FP32 SGD record eb51f539b5334bbf90d1a3afd6a2d2b5 and mixed FP16 AdamW record
  d44d7cd3f2e246ba9dcf17ba9921ddcf. Their measured work times were
  0.26134858292061836 and 0.36279399995692074 seconds. Reopening review then showed
  one compatible source each and estimates 0.32668572865077294 and
  0.45349249994615093 seconds, respectively, with unchanged memory/disk reserves.
  Canceling the renewed reviews created no additional runs or artifacts.
- Actual training still decreased loss (SGD 4.852477073669434 →
  4.686117172241211; AdamW 4.852474212646484 → 2.6992383003234863) and restored
  checkpoint state with 0.0 final parameter/moment errors. After app/backend
  restart all fourteen records, checkpoint restoration, saved CPU generation and
  both compatible estimates reopened exactly without further training. All
  seventy optimizer files, three source files and 245 prior artifact files
  retained their hashes. Evidence: /tmp/almg-estimate-native-qa/verification.json,
  post-run-estimates.json and native captures; generated artifacts remain outside Git.
- Validation: 600 Python tests passed with warnings as errors and Metal enabled,
  63 Flutter tests passed, and analysis was clean. Tests cover maximum observed
  time/headroom/provenance, changed initialization/config/runtime/producer,
  incomplete or tampered records, nonpositive/nonfinite times, actual measured
  optimizer feedback, unchanged reserves and estimated-versus-measured UI labels.
- Remaining: isolated peak profiling/calibration and broader training-feasibility
  estimates as the engine grows, unavailable Windows/CUDA and physical/oversized
  hardware checks, plus P3-LMF-06 corpus integration, independent continuation/
  cancellation and profiled 50M–100M training. These bounded synthetic timings do
  not establish large-model feasibility. Unchanged blockers stay open and skipped.

P3-LMF-06 partial progress · independently approved checkpoint continuation · 2026-11-20:
- [ ] P3-LMF-06 remains open. A saved bounded optimizer run now offers separate
  checkpoint-continuation review and explicit confirmation. It verifies the source
  record/checkpoint/optimizer hashes, current runtime/implementation and conservative
  hardware reserves, restores the midpoint model and SGD/AdamW state, and completes
  the original configuration/budget without resetting scheduler counters. Changed
  source/review, unsupported resources and malformed state cannot start. Full-run
  work estimates are deliberately not reused for the shorter continuation scope.
- A successful continuation writes a new private trained model, final optimizer
  state and versioned lineage record under decoder-optimizer-continuations. The
  original run, midpoint checkpoint and initialization stay unchanged. Final weights
  and CPU token generation must match the original completed reference run; loss
  must decrease from the restored checkpoint. Saved-history reads verify file hashes,
  parent/checkpoint lineage, moments/counters and CPU inference. Legacy source
  settings/checkpoints remain readable; UI history exposes retained continuations.
- Native verification: rebuilt and ran ALMG on this Mac with the isolated local
  8704-parameter two-layer initialization and external collection disabled.
  Reopened all fourteen copied source records before writes. Opened and canceled
  the first continuation review; no output directory/artifact was created. Then
  separately approved continuation of FP32 SGD source
  eb51f539b5334bbf90d1a3afd6a2d2b5 into 58b350c5d07848639d326a722519d079,
  and mixed FP16 AdamW source d44d7cd3f2e246ba9dcf17ba9921ddcf into
  1ffae4b267d34d55b30f5b9f8cc22da8. Both restored step ten and recorded exactly
  steps eleven through twenty, including the original gradient norms/clipping,
  learning rates and two-microbatch target counts. Final weights matched the
  original source final model with 0.0 error and identical CPU-generated token IDs.
- SGD loss fell from checkpoint loss 4.7254509925842285 to 4.686117172241211;
  AdamW loss fell 3.1773459911346436 → 2.6992383003234863. Final optimizer and
  scheduler counters were twenty. After app/backend restart all fourteen original
  runs and both independent continuations reopened exactly, including optimizer
  state validation and CPU inference. All six new continuation files, seventy
  original optimizer files, three initialization/source files and 315 prior
  artifact files retained their hashes. Evidence:
  /tmp/almg-continuation-native-qa/verification.json and native UI captures;
  generated datasets, checkpoints and weights remain outside Git.
- Validation: 603 Python tests passed with warnings as errors and Metal enabled,
  66 Flutter tests passed, and analysis was clean. Tests cover legacy ten-update
  SGD/step-five and mixed twenty-update AdamW/step-ten independent continuation,
  restored schedule cadence, immutable sources, explicit consent, changed-review/
  low-resource rejection, tampered source/output state and blocked/confirmed UI.
- Remaining: this verifies independent completion from an already verified saved
  midpoint, not recovery from arbitrary OS/process interruption. General durable
  interruption handling and graceful cancellation, approved text-corpus/tokenizer
  integration, broader budgets/resource monitoring and profiled 50M–100M training
  remain open. These synthetic runs do not establish language quality or release
  approval. Unchanged hardware/user-action blockers remain open and skipped.

P3-LMF-05 partial progress · fresh-worker optimizer peaks and calibrated reserves · 2026-11-20:
- [ ] P3-LMF-05 remains open. App-approved bounded optimizer training now executes
  in a new local Python/MLX worker for each run. Consent, current review/source,
  runtime and resource checks precede process launch and are checked again by the
  engine. The parent binds the response to its nonce, actual child PID, approved
  review and verified saved artifacts. Timeout/failure retains artifacts; no old
  checkpoint, weights or shared Metal counters are deleted/reset.
- The worker atomically augments its new saved run with versioned isolated peak
  RSS/Metal measurements and elapsed worker work, including bootstrap/imports,
  internal admission, both training trajectories, checkpoints and CPU inference.
  Process launch, parent admission, queue/approval waits and final measurement
  publication are excluded. Peak memory includes worker/runtime overhead. Legacy
  shared-process observations remain readable and explicitly distinct in the UI.
- Compatible isolated measurements update later preapproval review. The calculated
  memory reserve remains a floor; a derived floor sums observed fresh-process RSS
  and Metal peaks with 25% headroom, and can only raise admission above that
  calculated reserve. Unified memory may overlap, so the sum is conservative.
  Runtime/source/configuration/producer mismatch and non-isolated/invalid peaks
  are ignored. Work-time estimates prefer compatible fresh-worker observations.
  These measurements/heuristics are not large-model or exhaustion guarantees.
- Native verification: rebuilt and ran ALMG with the isolated local 8704-parameter
  two-layer initialization and external collection disabled. Reopened all sixteen
  retained optimizer/continuation records before writes. Explicitly approved
  twenty-update/two-microbatch FP32 SGD run d771750a3f814551822e03f618dfb691
  and mixed FP16 AdamW run 8bab00e00b934e3086ec6da1a83b2815. Their distinct
  worker PIDs were 57189/57387, separate from backend PID 51730. Measured SGD
  peak RSS/Metal were 76414976/212288 bytes with work time 0.5497713750228286 s;
  AdamW peaks were 82362368/246848 bytes with work time 0.5826146659674123 s.
- Renewed review showed one compatible isolated source each and work estimates
  0.6872142187785357/0.7282683324592654 s. Measured memory floors were below the
  existing conservative reserves, which correctly stayed 271505728/271784256
  bytes; disk reserves were unchanged. Canceling renewed reviews wrote no new
  training artifacts. Both actual runs decreased loss and retained 0.0 model/
  optimizer-state errors after midpoint checkpoint restoration.
- After app/backend restart all eighteen legacy/isolated/continuation records,
  CPU inference, measured peaks and calibrated memory/time reviews reopened
  exactly without additional training. All eighty-six optimizer/continuation
  files, three source files and 391 prior artifact files retained their hashes.
  Evidence: /tmp/almg-isolated-native-qa/verification.json, native captures and
  recovery-continue.log. Generated data, models and weights remain outside Git.
- Validation: 607 Python tests passed with warnings as errors and Metal enabled,
  67 Flutter tests passed, and analysis was clean. Tests cover real fresh-worker
  SGD/AdamW execution, process separation, consent/review gating before launch,
  compatible-only peak calibration, upward-floor low-memory rejection before
  launch, no reserve reduction, source preservation,
  persisted records and isolated-versus-shared UI labels.
- Remaining: broader engine/continuation peak profiling, arbitrary interruption/
  cancellation, text-corpus integration and the profiled 50M–100M target. Bounded
  synthetic fixtures remain capped at 16384 parameters. Windows/CUDA, physical
  power and oversized-fixture blockers remain open and skipped unchanged.

P3-LMF-05 partial progress · isolated checkpoint-continuation peak feedback · 2026-11-20:
- [ ] P3-LMF-05 remains open. Separately approved optimizer checkpoint continuation
  now runs in a fresh local worker, with the same consent/review/resource checks,
  nonce/PID binding, retained-artifact behavior and atomic measurement publication
  as bounded fresh training. Normal training and continuation use distinct measured
  formats/scopes; the latter measures only remaining original updates plus bootstrap,
  admission, restoration and final CPU inference. Shared counters are never reset.
- Continuation review derives its own memory/time feedback from verified isolated
  continuation records matching the exact parent/checkpoint hashes, configuration,
  runtime and producer. Full-training timing is not reused. Work estimates use the
  highest compatible observation plus 25% headroom; a derived memory floor sums
  isolated RSS/Metal peaks with the same headroom and never reduces the preexisting
  admission reserve. Changed checkpoint state/context, unfinished/non-isolated
  records and malformed peaks are ignored. Above-reserve measured floors block
  machines that cover only the smaller calculated reserve before worker launch.
- The app labels measured continuation peaks/work separately from estimated
  remaining checkpoint work, and explains bootstrap/restore/inference overhead,
  exclusions and scope. Old normal and continuation records remain readable.
  No arbitrary-interruption, extended-budget or total wall-time claim is added.
- Native verification: rebuilt and ran ALMG with the isolated local 8704-parameter
  two-layer initialization and external collection disabled. Reopened all eighteen
  retained records before writes. From previously isolated normal-training sources
  d771750a3f814551822e03f618dfb691 (FP32 SGD) and
  8bab00e00b934e3086ec6da1a83b2815 (mixed FP16 AdamW), separately approved
  continuations 1bca6effdcd2431c84df2564e759ac44 and
  127330e5dcb341c28d14e51b695bd466. Canceling the first review created no artifact.
  Fresh worker PIDs 86271/86380 were distinct from backend PID 81774 and each other.
- SGD measured 0.4200614580186084 s with peak RSS/Metal 74432512/140144 bytes;
  AdamW measured 0.43341808300465345 s with peaks 76382208/171376 bytes. Each
  restored step ten, completed exactly steps eleven through twenty with the original
  scheduler/gradient/clipping trace, matched source final weights with 0.0 error
  and reproduced source CPU-generated token IDs. SGD loss fell 4.7254509925842285 →
  4.686117172241211; AdamW loss fell 3.1773459911346436 → 2.6992383003234863.
- Refreshed continuation reviews showed one compatible source each and remaining-
  work estimates 0.5250768225232605/0.5417726037558168 s. Memory reserves correctly
  stayed at their larger existing 271505728/271784256-byte floors. Closing those
  reviews produced no extra training. After app/backend restart all twenty records,
  optimizer state, CPU inference and both continuation-specific calibrations
  reopened exactly. All ninety-two optimizer/continuation files, three source files
  and 477 prior artifact files retained their hashes. Evidence:
  /tmp/almg-continuation-peaks-native-qa/verification.json and native captures;
  generated datasets, checkpoints and weights remain outside Git.
- Validation: 610 Python tests passed with warnings as errors and Metal enabled,
  68 Flutter tests passed, and analysis was clean. Tests cover normal and continuation
  worker execution, legacy state/schedule preservation, exact-checkpoint context
  rejection, separate-scope feedback, measured-floor admission blocking before
  launch, source preservation and measured-versus-estimated continuation UI.
- Remaining: broader corpus/engine profiling as P3-LMF-06 grows, arbitrary durable
  interruption and graceful cancellation, text-corpus integration and profiled
  50M–100M training. Current synthetic fixtures remain capped at 16384 parameters.
  Unchanged Windows/CUDA, physical power and oversized-fixture blockers remain open
  and skipped; bounded observations do not establish large-model feasibility.

P3-LMF-06 partial progress · cooperative continuation cancellation · 2026-11-21:
- [ ] P3-LMF-06 remains open. Running checkpoint continuation now exposes an
  explicit cancel action tied to a fresh per-request token. A separate backend
  request persists a consented, versioned intent bound to the exact parent record
  revision. The worker checks between optimizer updates, finishes any update in
  progress and retains a new private partial model, moments and scheduler counter.
  It is never killed for cancellation and original models/checkpoints stay unchanged.
  A request arriving before worker execution is honored at the restored checkpoint.
- New continuation records use version-2 terminal status (completed/canceled) and
  cancellation provenance. Readers retain version-1 completed compatibility and
  validate partial counter ranges, scheduler/log cadence, model configuration,
  moment shapes/finiteness, file hashes, parent lineage and own CPU inference.
  Canceled records do not claim final-model equivalence or release approval and
  cannot feed completed-work calibration. The UI distinguishes retained partial
  state from completed output. Continuing a canceled partial artifact through the
  app is not yet exposed; general fresh-run cancellation remains separate/open.
- Native verification: rebuilt and ran ALMG with the isolated local 8704-parameter
  two-layer initialization and external collection disabled. Reopened all twenty
  retained v1 records before writes. Used a local pacing fixture only to exercise
  live cancel clicks after real SGD/AdamW updates; ordinary completions used the
  unmodified worker path. From FP32 SGD source d771750a3f814551822e03f618dfb691,
  canceling continuation f700a12756864ffb8983f7629acf15df stopped at update eleven
  and saved scheduler counter eleven, model/state and a scoped cancellation intent.
  Its loss moved 4.7254509925842285 → 4.7173380851745605. Mixed FP16 AdamW source
  8bab00e00b934e3086ec6da1a83b2815 canceled into
  892d76ba946741d880e3dc303e110a9e at update eleven, retaining nonempty moments
  and loss 3.1773459911346436 → 3.076367139816284. Both recorded exactly the
  original step-eleven gradient/clipping/scheduler trace and stayed unreleased.
- Renewed reviews excluded both canceled samples. Separately approved uncanceled
  continuations 39fe60a10e7a4152a2c6e42b321e4020 (SGD) and
  ae6b89dde53b4ddc98818241cee077a7 (AdamW) completed step twenty with 0.0 source
  final-weight error and identical source CPU token generation. Later calibration
  used only the one completed sample for each parent, never the paced canceled work.
- After app/backend restart all twenty-four legacy/v2 completed/canceled records,
  private partial state, cancellation intents and CPU inference reopened exactly.
  All 106 optimizer/continuation/cancellation files, three source files and 569 prior
  artifact files retained their hashes. Evidence:
  /tmp/almg-cancel-native-qa/verification.json and native UI captures; generated
  datasets, models, checkpoints and cancellation intents remain outside Git.
- Validation: 612 Python tests passed with warnings as errors and Metal enabled,
  69 Flutter tests passed, and analysis was clean. Tests cover intent consent/
  token/source/revision binding, tampering, queued cross-process cancellation,
  safe mid-update cancellation, v1/v2 reads, active-token UI and calibration exclusion.
  A numerical recovery test loaded saved step-twelve mixed AdamW partial state and
  finished in memory to reproduce every original final parameter exactly, proving
  retained moments/scheduler state are usable without exposing an unverified UI path.
- Remaining: app approval/resume from canceled partial artifacts, arbitrary durable
  OS/process interruption, general fresh-run cancellation, approved text-corpus/
  tokenizer integration, broader budgets/resource profiling and profiled 50M–100M
  training. Current synthetic fixtures remain capped at 16384 parameters. Unchanged
  hardware/user-action blockers stay open and skipped; language quality and release
  acceptance are not established by these fixture checks.

P3-LMF-06 partial progress · approved retained-partial checkpoint resume · 2026-11-21:
- [ ] P3-LMF-06 remains open. A canceled private checkpoint now offers a separate
  partial-resume review and explicit approval. The review binds the exact partial
  record/model/optimizer hashes, actual retained update, original configuration,
  runtime, producer and conservative reserves. Resume restores the retained model,
  moments and scheduler counter rather than restarting at the original midpoint.
  Only canceled sources with remaining original work can resume; completed sources,
  changed state/review, cyclic lineage and over-depth ancestry are rejected.
- Version-3 continuation records retain immutable ancestry through repeated
  cancel/resume steps while preserving version-1/2 reads. Every new result stays
  private and validates its ancestor chain, saved counters/moments/configuration,
  file hashes and own CPU inference. Completed results must match the original
  reference final weights and CPU token output. Partial-resume cancellation is
  separately token-bound to the partial source kind/ID/revision. Remaining-work
  feedback matches the exact retained source and restore step and cannot leak into
  original-midpoint estimates. Canceled samples remain excluded from forecasts.
- Native verification: rebuilt and ran ALMG with the isolated local 8704-parameter
  two-layer initialization and external collection disabled. Reopened all twenty-
  four retained records before writes. Reviewed saved step-eleven canceled sources
  f700a12756864ffb8983f7629acf15df (FP32 SGD) and
  892d76ba946741d880e3dc303e110a9e (mixed FP16 AdamW); the app correctly showed
  restore step eleven and nine remaining updates. Closing the first review created
  no output. Explicitly resumed both, then used local pacing only to exercise live
  re-cancellation: new canceled records 63916dba38c047cea204d90d5e16ca7f and
  a8d0eaa53a0d4ca192e7a08e1ef7e2c1 stopped safely at update twelve, preserving
  the exact original step-twelve gradient/clipping/scheduler trace and private state.
- Separately approved those new step-twelve checkpoints and resumed without pacing
  into 535648f8eacf4cd4840f48a02db34f0e (SGD) and
  bd3d0325edb2466e8da7998e22bd2217 (AdamW). Both restored counter twelve,
  recorded exactly steps thirteen through twenty, finished scheduler/optimizer
  counter twenty and matched every original final parameter with 0.0 error and
  identical CPU-generated token IDs. Final losses were 4.686117172241211 (SGD)
  and 2.6992383003234863 (AdamW). All partial ancestors and original sources stayed
  unchanged and unreleased. Feedback used only the matching completed partial
  resume and was not reused for the original midpoint review.
- After app/backend restart all twenty-eight v1/v2/v3 legacy/canceled/completed
  records, partial ancestry, optimizer state, CPU inference and scoped feedback
  reopened exactly without further training. All 120 optimizer/continuation/
  cancellation files, three source files and 675 prior artifact files retained
  their hashes. Evidence: /tmp/almg-partial-resume-native-qa/verification.json and
  native captures; generated datasets, checkpoints, weights and intents remain
  outside Git.
- Validation: 615 Python tests passed with warnings as errors and Metal enabled,
  70 Flutter tests passed, and analysis was clean. Tests cover real SGD/mixed AdamW
  partial recovery, restored schedule/gradient traces and exact final models,
  completed/corrupt-source rejection, consent, re-cancellation and chained recovery,
  cyclic ancestry, source immutability, scoped feedback and explicit UI review.
- Remaining: arbitrary durable OS/process interruption, general fresh-run
  cancellation, approved text-corpus/tokenizer integration, broader budgets/resource
  profiling and profiled 50M–100M training. Lineage validation is bounded to sixteen
  continuation records. Current synthetic fixtures remain capped at 16384 parameters;
  these checks establish checkpoint engineering, not language quality or release
  acceptance. Unchanged hardware/user-action blockers remain open and skipped.

P3-LMF-06 partial progress · reviewed corpus input snapshots · 2026-11-21:
- [ ] P3-LMF-06 remains open. Initialized planned decoders now expose “Review text
  corpus inputs”. Select an existing prepared local dataset and sequence length
  four/eight, review compatibility, then explicitly confirm saving private inputs.
  Existing dataset integrity, fitted-tokenizer and cross-split contamination checks
  apply. Every source requires a recorded creation/permission declaration; pending
  sources, mismatched model/tokenizer vocabulary, oversized models/windows and
  insufficient model context block saving. Changed reviews require a fresh check.
- New version-1 immutable snapshots bind the initialization/model hash, exact dataset
  revision, tokenizer artifact, sequence length and window digest. Windows preserve
  document boundaries, cover each real target once before training-only sampling
  weights, right-pad with masked targets, and retain separate validation/test inputs.
  Save publishes atomically and read verifies every file/review binding. Original
  datasets, tokenizer and initialized weights are preserved. No training approval
  transfers to these inputs and saving performs no optimizer updates.
- Local app verification: rebuilt/launched ALMG with a generated six-document,
  four-word corpus and a fresh 704-parameter initialization. The native app blocked
  six unresolved source permissions, then accepted the reviewed dataset. Closing
  before confirmation created no output. Confirmed save produced private record
  ec05cf95ac73467f87d33a0317a3bda3: train six windows/38 real targets, validation
  two windows/10 targets, test two windows/nine targets. Reopened the exact record
  from history and again after restarting app/backend. The same reviewed tokenizer
  was rejected for the retained 128-ID initialization. All 143 original fixture
  files retained their hashes. No external collection occurred. Evidence:
  /tmp/almg-corpus-input-native-qa/verification.json and native captures
  permissions-blocked-ui.json, compatible-ui.json, saved-ui.json,
  restarted-ui.json and vocabulary-blocked-ui.json.
- Validation: 618 Python tests passed with warnings as errors and Metal enabled;
  71 Flutter tests passed; analysis clean. New tests cover exact review/consent,
  source permission/vocabulary blocking, masked document windows, target counts,
  training-only weighting, corrupt snapshot rejection, preserved source files and
  UI approval invalidation. Generated fixtures, snapshots and weights stay out of Git.
- Remaining: connect these reviewed snapshots to configurable optimizer execution,
  corpus loss/evaluation and tokenizer-backed generation/checkpoint continuation;
  general fresh-run cancellation, durable OS interruption, larger budgets and
  profiled 50M–100M training remain open. This input-preparation change does not
  establish corpus training, language quality or release acceptance. P3-LMF-01 is
  already complete for its recorded architecture scope. Unchanged blocked items
  remain open and skipped.

P3-LMF-06 partial progress · approved reviewed-corpus optimizer training · 2026-11-21:
- [ ] P3-LMF-06 remains open. Saved corpus-input snapshots now offer a separate
  optimizer resource review and explicit training confirmation. Bounded FP32 SGD
  or AdamW runs use the saved four/eight-token document windows, one row/microbatch
  per update and ten/twenty updates. Settings retain version-5 scheduling, clipping,
  fixed seed from the fresh initialization and optimizer-state contracts. Every
  training window must be visited at least once; snapshots/configuration/source
  hashes and implementation/runtime bindings are rechecked before execution.
- Corpus admission adds snapshot storage/load and optimizer moments to conservative
  model reserves and rechecks current hardware availability. Training runs on the
  existing serial GPU worker. Every update records its deterministic corpus window
  index and real masked target count. All saved train/validation/test windows are
  scored separately using target-token-weighted loss. A midpoint model plus moments
  and scheduler counter is saved/restored; continued execution must exactly match a
  separately executed uninterrupted trajectory. Failed checks retain any checkpoint
  for inspection instead of publishing a completed record.
- Private version-1 results retain trained weights, tokenizer, midpoint checkpoint,
  approval/admission/configuration and source lineage, loss diagnostics, update logs
  and explicitly shared-process time/memory observations. CPU inference must match
  Metal within tolerance; saved model/tokenizer reload must reproduce generated
  text. History validates every artifact hash, corpus/tokenizer binding, checkpoint
  state and CPU generation. Original input snapshots, datasets and fresh weights
  are preserved; no supervisor weights initialize the student and release stays off.
- Native verification: rebuilt/launched ALMG against isolated local fixtures and
  reopened saved corpus ec05cf95ac73467f87d33a0317a3bda3 for a fresh 704-parameter
  model. Closing resource review created no training output. Explicitly trained
  twenty-update SGD run f0a8d481e17b4ff0b22b70501a351b2b and AdamW run
  7008809d52314cdbbe4a79760cc0df5e. Train loss 1.3801190426 decreased to
  1.2617147935 (SGD) / 0.7957110165 (AdamW); validation 1.4003016328 decreased to
  1.3241882882 / 0.8205200584; test 1.3769487855 decreased to 1.2886807562 /
  0.8194744578. Both restored update ten, finished optimizer/scheduler update twenty
  and matched uninterrupted weights and moments with 0.0 error. CPU/Metal errors
  were 1.24e-8 / 9.24e-8. Saved CPU models generated eleven corpus words using
  their own tokenizers; these toy-corpus results establish engineering only.
- Both native histories reopened exactly before and after app/backend restart,
  revalidating checkpoint state and CPU-generated text without further training.
  All 149 original fixture files retained their hashes. Evidence:
  /tmp/almg-corpus-training-native-qa/verification.json, sgd-review-ui.json,
  sgd-trained-ui.json, adamw-trained-ui.json, sgd-restarted-ui.json and
  adamw-restarted-ui.json. No external collection occurred. Generated datasets,
  input snapshots, checkpoints, tokenizer artifacts and weights remain outside Git.
- Validation: 620 Python tests passed with warnings as errors and Metal enabled,
  72 Flutter tests passed, analysis clean. New coverage exercises actual SGD/AdamW
  corpus updates, checkpoint/optimizer/scheduler restoration and exact comparison,
  reloaded tokenizer-backed CPU generation, source preservation, corrupted artifacts,
  resource/consent/stale-review rejection, settings invalidation and saved results.
- Remaining: independent corpus-checkpoint continuation/cancellation, corpus mixed
  precision/accumulation and batch controls, durable OS/process interruption, larger
  budgets, broader quality evaluation and profiled 50M–100M training. Existing
  synthetic optimizer paths retain their richer controls and unchanged formats.
  P3-LMF-01 is already complete for its recorded architecture scope. Unchanged
  hardware/user-action blockers remain open and skipped.

P3-LMF-06 partial progress · token-weighted corpus gradient accumulation · 2026-11-21:
- [ ] P3-LMF-06 remains open. Reviewed text-corpus training now offers effective
  batch sizes one/two and one/two microbatches per optimizer update. Changes clear
  approval and require a fresh resource review. Two microbatches require batch two;
  selected batch must fit the initialized plan. Admission includes accumulation
  buffers and requires enough updates to visit every saved training window.
- Window selection derives from restored optimizer step and selected effective
  batch, preserving the same corpus schedule through checkpoint restore. Gradients
  from unequal masked windows are averaged by real target-token count, then clipped
  and applied once. Every two-way accumulated update is checked against its full
  effective-batch gradient within FP32 tolerance 1e-5. Checkpointed execution must
  still match uninterrupted weights/moments within 1e-7; scheduler counters count
  optimizer updates rather than microbatches.
- New version-2 reviews/results record effective rows, accumulation count, gradient
  comparison/tolerance and exact per-update window indices/target counts. Saved
  reads verify counters and window bindings against the immutable corpus snapshot.
  Version-1 single-row records retain their exact read behavior and original files;
  no stored artifact is rewritten or silently migrated.
- Native verification: rebuilt/launched ALMG with the retained four-word corpus,
  six unequal training windows and fresh 704-parameter initialization. Reopened
  both existing v1 SGD/AdamW records exactly. The app blocked batch one with two
  microbatches, accepted batch two/two microbatches after a new review, and closing
  before training confirmation created no output. Explicitly completed twenty-update
  SGD 9402ab563e10473cbc660aa7386926d3 and AdamW
  dd58589860a3419483c61d299ced6f68. Each first batch combined eight/four real
  targets (twelve total); update logs retained both window indices and microbatches.
  Maximum full/accumulated gradient differences were 8.9406967e-8 / 1.1920929e-7.
- Both native runs restored midpoint update ten, finished optimizer/scheduler update
  twenty and matched uninterrupted final weights and moments with 0.0 error. Train
  loss 1.3801190426 decreased to 1.2491788146 (SGD) / 0.7765748561 (AdamW);
  validation/test losses also decreased. Reloaded private models generated corpus
  words through their own CPU runtime/tokenizer. These are toy-corpus engineering
  diagnostics and establish no language-quality or release acceptance.
- After app/backend restart all four v1/v2 records, checkpoint state, generated text
  and window/update metadata reopened exactly without further training. All 163
  original fixture files retained their hashes. Evidence:
  /tmp/almg-corpus-accumulation-native-qa/verification.json, incompatible-ui.json,
  compatible-ui.json, sgd-trained-ui.json, adamw-trained-ui.json and restarted
  native captures. No external collection occurred; generated artifacts/weights
  remain outside Git.
- Validation: 621 Python tests passed with warnings as errors and Metal enabled,
  73 Flutter tests passed, analysis clean. Real SGD/AdamW tests compare batch-two
  full and accumulated execution over unequal padding, restore optimizer/scheduler
  state, verify per-update target counts and reject modified saved update bindings.
  UI tests cover incompatible configuration, fresh approval and selection changes.
- Remaining: corpus mixed precision, independently approved corpus checkpoint
  continuation/cancellation, durable OS/process interruption, larger budgets,
  broader quality evaluation and profiled 50M–100M training. Unchanged independent
  hardware/user-action blockers remain open and skipped.

P3-LMF-06 partial progress · bounded mixed FP16 corpus training · 2026-11-21:
- [ ] P3-LMF-06 remains open. Reviewed-corpus optimizer controls now select FP32 or
  bounded mixed FP16 computation. Changing precision invalidates approval. Version-3
  reviews/results bind selected precision and fixed loss scale (128 mixed / 1 FP32),
  while retaining conservative FP32 memory reserves. No memory-saving or isolated
  peak claim is made. Existing v1/v2 records remain readable without rewriting.
- Mixed matrix products use the established bounded FP16 implementation with FP32
  normalization/softmax/loss and master weights/gradients/optimizer moments. Scaled
  gradients must be finite FP32, are unscaled before token-weighted accumulation,
  then clipped and applied once per optimizer update. Accumulated/full gradients
  must agree within mixed tolerance 1e-3 (FP32 retains 1e-5). Initial selected loss
  is checked against FP32 within .05 and future tokens cannot affect the causal
  prefix. Final selected/FP32 logits must agree within .05; FP32 Metal/CPU inference
  retains tolerance 1e-5. Checkpointed weights/moments retain tolerance 1e-7.
- Saved precision metadata/checks are validated on read, including fixed scaling,
  FP32 master-state declarations and precision-specific accumulation tolerance.
  Reported train/validation/test losses explicitly evaluate the saved FP32 master
  model; independent continuation and cancellation remain unavailable on this path.
- Native verification: rebuilt/launched ALMG with retained permission-reviewed local
  corpus and fresh 704-parameter initialization. Reopened all four v1/v2 records
  exactly, compared FP32/mixed SGD resource reviews (same calculated reserve), and
  confirmed closing review created no output. Explicitly completed mixed FP16,
  batch-two/two-microbatch SGD 2af62133aea74f7fad00666cf39e80ba and AdamW
  f15c14ccde1049ba928ecaa17ae53f40. Both restored step ten and finished optimizer/
  scheduler step twenty, matching uninterrupted final weights/moments with 0.0 error.
- Initial precision-loss difference was 8.3446503e-6 and causal-prefix error 0.0.
  Maximum full/accumulated gradient differences were .0004660785 (SGD) /
  .0002848357 (AdamW); final selected/FP32 logit differences .0000991970 /
  .0003766716. FP32 Metal/CPU errors were 2.91e-8 / 5.58e-8. Train loss
  1.3801190426 decreased to 1.2491794805 / .7765709044; validation/test losses
  also decreased. Reloaded private models generated corpus words through their own
  CPU runtime/tokenizer. These toy-corpus checks establish bounded engineering,
  not general mixed-precision stability, language quality or release acceptance.
- After app/backend restart all six v1/v2/v3 records, precision metadata, checkpoint
  states and generated text reopened exactly without further training. All 177
  original fixture files retained their hashes. Evidence:
  /tmp/almg-corpus-mixed-native-qa/verification.json, fp32-review-ui.json,
  mixed-review-ui.json, sgd-trained-ui.json, adamw-trained-ui.json and restarted
  native captures. No external collection occurred; generated artifacts and weights
  remain outside Git.
- Validation: 622 Python tests passed with warnings as errors and Metal enabled,
  74 Flutter tests passed, analysis clean. New real mixed SGD/AdamW coverage checks
  unscaled masked accumulation, decreasing master-model loss, FP32 checkpoint
  weights/moments, restored counters, precision/causal/CPU compatibility, unchanged
  sources and rejection of changed saved scaling. UI tests verify precision changes
  clear approval and submit fixed scaling. Incorrect settings are rejected.
- Remaining: independently approved corpus checkpoint continuation/cancellation,
  durable OS/process interruption, larger budgets/resource profiling, broader quality
  evaluation and profiled 50M–100M training. Unchanged independent hardware/user-
  action blockers remain open and skipped.

P3-LMF-06 partial progress · independently approved corpus checkpoint continuation · 2026-11-21:
- [ ] P3-LMF-06 remains open. Saved corpus optimizer runs now offer a separate
  midpoint-continuation review and explicit confirmation. Review binds the original
  record/revision, checkpoint/model/optimizer hashes, corpus revision, original
  configuration/precision, runtime, implementation and current conservative resource
  admission. Closing or declining creates no continuation output; stale review,
  changed source state and insufficient resources reject execution.
- Continuation restores the retained midpoint model, FP32 optimizer moments and
  scheduler counter, then executes only the remaining original updates into new
  private artifacts. A shared corpus update routine preserves original step-derived
  window selection, masked token weighting, scaling, clipping and learning rates.
  This replays a completed run's retained midpoint; arbitrary crash/OS interruption
  recovery and cancellation are not established by this change.
- Separate version-1 continuation records retain immutable parent/checkpoint/corpus
  lineage, actual restored/completed counters, remaining update logs, split losses,
  generated text, trained model, tokenizer and final FP32 optimizer state. Records
  publish atomically after checks. Final weights must match the original saved model
  within 1e-7 and CPU generation must match exactly. Reads revalidate file hashes,
  original source/checkpoint bindings, moment shapes/finite values/counters, exact
  window/target/learning-rate schedule, final reference weights and tokenizer-backed
  CPU inference. Shared-process observations do not claim isolated peaks or forecasts.
- Native verification: rebuilt/launched ALMG with retained local corpus fixtures and
  reopened all six v1/v2/v3 source runs exactly. Reviewed legacy FP32 SGD source
  f0a8d481e17b4ff0b22b70501a351b2b and mixed FP16 AdamW source
  f15c14ccde1049ba928ecaa17ae53f40. Reviews showed restore update ten, ten remaining
  updates and zero reference-retraining updates. Closing the first review created
  no artifact. Explicit confirmation produced SGD continuation
  6a3cf68b11504259b012a1879e5050ce and AdamW
  b8117bd1c8ea495c9e637ee431df4c9b, each recording only updates eleven through
  twenty and finishing optimizer/scheduler counter twenty.
- Both native results matched original final weights with 0.0 error and identical
  CPU-generated token IDs/text. Train loss from restored checkpoints decreased
  1.2918970995 → 1.2617147935 (SGD) and .9098939715 → .7765709044 (AdamW);
  validation/test losses also decreased. AdamW used original batch-two, two-way
  accumulation and fixed-scale mixed computation; SGD preserved its legacy one-row
  FP32 configuration. These toy-corpus checks establish checkpoint engineering,
  not language-quality or release acceptance.
- After app/backend restart all eight source/continuation records, final optimizer
  states, checkpoint lineage and CPU text reopened exactly without further training.
  All 191 original fixture files retained their hashes. Evidence:
  /tmp/almg-corpus-continuation-native-qa/verification.json, sgd-review-ui.json,
  adamw-review-ui.json, sgd-continued-ui.json, adamw-continued-ui.json and restarted
  native captures. No external collection occurred; generated artifacts, tokenizers
  and weights remain outside Git.
- Validation: 624 Python tests passed with warnings as errors and Metal enabled,
  75 Flutter tests passed, analysis clean. New real FP32 SGD/mixed AdamW tests verify
  remaining-only execution, restored state/schedule and final reference inference,
  source preservation, scoped history, consent/resource/stale-review rejection,
  corrupted checkpoint/final state rejection and changed saved learning-rate logs.
  UI tests cover separate review, blocked resources and explicit confirmation.
- Remaining: corpus continuation/fresh-run cancellation, retained partial recovery,
  arbitrary durable OS/process interruption, larger budgets/resource profiling,
  broader quality evaluation and profiled 50M–100M training. Independent unchanged
  hardware/user-action blockers remain open and skipped.

P3-LMF-06 partial progress · cooperative corpus continuation cancellation · 2026-11-21:
- [ ] P3-LMF-06 remains open. Running corpus checkpoint continuation now exposes
  Cancel. Each app run gets a fresh bounded random token; explicit cancellation
  writes an atomic receipt bound to that token and original corpus run/revision.
  Requests are handled outside the GPU queue and checked between complete optimizer
  updates. No worker is killed and no source, checkpoint or trained weight is deleted.
  A late request can finish as completed if no original work remains.
- New version-2 continuation records distinguish completed and canceled outcomes.
  Canceled results retain actual model, FP32 optimizer moments and scheduler counter,
  tokenizer, executed update log and own CPU-generated text. They do not claim final
  reference matching, decreasing loss or release acceptance. Cancellation before the
  first new update can retain the restored midpoint unchanged. Reads validate receipt
  ownership, status/counter ranges, optimizer state, exact executed window/schedule
  and private CPU inference. Existing v1 completed records remain readable unchanged.
- Native verification: rebuilt/launched ALMG, reopened all eight prior source/v1
  continuation records exactly, and explicitly continued the retained FP32 SGD and
  mixed FP16 AdamW sources. A local fixture delay only made the ten-update runs
  observable for live Cancel; student gradients, updates and persistence were real.
  Clicking Cancel stopped both at update eleven: private canceled SGD
  0ad9d3c9c5f04b549372cb3d3a2343cf and AdamW
  7ed1874d6ed44d12a5f72bd5c5d87e9c retained one new update, scheduler counter eleven
  and matching saved optimizer state. Their reference-match fields stayed null.
- Removed pacing and separately approved original-midpoint completion with new app
  tokens. SGD 3cbaae77022d4e179dbbe78f824ca7da and AdamW
  a227a54fe9c5470883735cc7efdaa355 completed update twenty, matched original final
  weights with 0.0 error and identical CPU token output. Old cancellation receipts
  did not stop these newly approved runs. This repeats the original midpoint work;
  it does not resume the newly canceled update-eleven partials, which remain private.
- After app/backend restart all twelve original/v1/v2 completed/canceled records,
  partial state/counters, receipt bindings and CPU text reopened exactly without
  further training. All 201 original fixture files and all 221 retained files
  (including new model/state/receipt and fixture files) retained their hashes.
  Evidence: /tmp/almg-corpus-cancel-native-qa/verification.json,
  sgd-canceled-ui.json, adamw-canceled-ui.json, sgd-completed-ui.json,
  adamw-completed-ui.json and restarted native captures. No external collection
  occurred; generated artifacts, receipts, tokenizers and weights remain outside Git.
- Validation: 626 Python tests passed with warnings as errors and Metal enabled,
  76 Flutter tests passed, analysis clean. Real FP32 SGD/mixed AdamW coverage checks
  stop-after-update and stop-before-first-update behavior, retained moments/counters,
  source preservation, receipt idempotence/token isolation, malformed receipt rejection,
  legacy completed reads and normal completion. UI tests verify the active run token,
  cancellation while a request is in flight, waiting feedback and retained status.
- Remaining: independently approved retained-partial corpus resume, fresh corpus-run
  cancellation, arbitrary durable OS/process interruption, larger budgets/resource
  profiling, broader quality evaluation and profiled 50M–100M training. Unchanged
  independent hardware/user-action blockers remain open and skipped.

P3-LMF-06 partial progress · approved retained-partial corpus resume · 2026-11-21:
- [ ] P3-LMF-06 remains open. A canceled corpus continuation now offers separate
  retained-partial review and explicit resume confirmation. Review binds the exact
  partial ID/revision, model/optimizer hashes, actual counter, original corpus and
  configuration/precision, runtime and conservative admission. Only canceled sources
  with original work remaining can resume. Completed sources, stale reviews, corrupt
  state, cyclic ancestry and over-depth lineage reject execution.
- Resume restores the retained model, FP32 optimizer moments and actual scheduler
  counter, preserving the original step-derived corpus windows and learning rates.
  New version-3 private records retain immutable ancestry through repeated resume/
  cancel operations. Both source partial and original run remain unchanged. Reads
  verify the ancestor chain, saved counters/state, window/target/schedule trace,
  file hashes and own CPU inference. Completed descendants must match the original
  final model within 1e-7 and generated token IDs/text exactly. Lineage is bounded
  to sixteen records; arbitrary interrupted-process recovery is not established.
- Resume cancellation uses a distinct partial-source kind and its ID/revision, with
  a fresh run token. Version-2 cancellation receipts support original/partial source
  kinds; existing version-1 receipts and v1/v2 continuation records remain readable
  without rewriting. A retained partial can be re-canceled safely, then separately
  reviewed again from its newly saved actual update rather than the old midpoint.
- Native verification: rebuilt/launched ALMG and reopened all twelve prior records
  exactly. Reviewed canceled update-eleven SGD 0ad9d3c9c5f04b549372cb3d3a2343cf and
  mixed FP16 AdamW 7ed1874d6ed44d12a5f72bd5c5d87e9c; reviews showed restore eleven
  and nine remaining updates with matching partial optimizer hashes. Closing the
  first review created no output. Explicitly resumed both; local pacing only made
  live re-cancellation observable. New canceled records
  ac4df9d1fc4247e1b4253eb147b2e611 (SGD) and
  2a2801524a604a2999788e6b983ebd3c (AdamW) restored eleven and retained update twelve,
  with depth-two ancestry and actual model/moment/scheduler state.
- Removed pacing and separately approved those update-twelve partials. Completed
  SGD 8158a8135d7147768e8cafda1984ab6b and AdamW
  46a9d0a6cc3f43ffb685806b1ec49b92 restored twelve, recorded only updates thirteen
  through twenty and finished optimizer/scheduler counter twenty. Both matched
  original final weights with 0.0 error and identical CPU-generated tokens/text.
  Depth-three records bind both retained ancestors. These are toy-corpus checkpoint
  engineering checks, not language-quality or release acceptance.
- After app/backend restart all sixteen legacy/canceled/resumed records, ancestry,
  receipt kinds, optimizer states/counters and CPU text reopened exactly without
  further training. All 221 original fixture files and all 241 retained files kept
  their hashes. Evidence: /tmp/almg-corpus-partial-native-qa/verification.json,
  sgd-partial-review-ui.json, adamw-partial-review-ui.json, sgd-recanceled-ui.json,
  adamw-recanceled-ui.json, sgd-completed-ui.json, adamw-completed-ui.json and
  restarted native captures. No external collection occurred; generated artifacts,
  receipts, tokenizers and weights remain outside Git.
- Validation: 627 Python tests passed with warnings as errors and Metal enabled,
  77 Flutter tests passed, analysis clean. New real FP32 SGD/mixed AdamW coverage
  checks chained state/schedule recovery, exact final reference inference, immutable
  ancestors, completed-source/stale-review rejection, cancellation source isolation,
  cyclic and depth-limit rejection. UI tests verify separate partial review/resume
  routes and actual retained counters; native checks exercise live partial Cancel.
- Remaining: fresh corpus-run cancellation, arbitrary durable OS/process interruption,
  larger budgets/resource profiling, broader quality evaluation and profiled 50M–100M
  training. Corpus-engine peak profiling under P3-LMF-05 is independently actionable
  with this bounded engine. Unchanged independent hardware/user-action blockers
  remain open and skipped.

P3-LMF-05 partial progress · isolated reviewed-corpus peaks and scoped feedback · 2026-11-21:
- [ ] P3-LMF-05 remains open. New app-approved corpus optimizer runs execute in a
  fresh local process after parent admission, then recheck approval/resources inside
  that worker. A nonce/actual child-PID/source/corpus/approval binding is checked
  before returning the saved result. Worker failure or timeout retains any model/
  checkpoint artifacts. Existing direct/shared corpus records remain readable;
  corpus continuation and partial-resume execution stay on their existing path.
- New version-1 isolated corpus measurements record module-entry workflow elapsed
  time, process-lifetime RSS peak and Metal peak, including imports/admission/history
  validation, model/corpus loading, both training verification trajectories,
  checkpoint work, split evaluation and CPU generation. Timing excludes parent
  admission, subprocess launch/pre-module startup, queue/approval waits and final
  measurement publication. Peaks include runtime overhead and may overlap in unified
  memory. No shared counters are reset; no large-model feasibility is inferred.
- Version-4 isolated corpus reviews use only verified completed observations matching
  exact initialization, corpus ID/revision, optimizer/batch/precision/budget, model
  configuration, runtime/topology, execution policy and producer. Work estimates use
  the largest compatible measured time plus 25% headroom and are explicitly heuristic.
  Memory calibration calculates (RSS + Metal) with 25% headroom and can raise the
  required reserve, never reduce its calculated baseline. Current availability is
  rechecked against the resulting reserve before spawning a worker. Shared/legacy,
  different-corpus/configuration/runtime/producer observations cannot enter feedback.
- Native verification: rebuilt/launched ALMG and reopened all sixteen original/
  canceled/resumed records exactly. Closing the first isolated review created no
  output. Explicitly trained the retained 704-parameter local corpus with batch two,
  two-way accumulation and twenty updates: FP32 SGD
  d5be342535d2487e8ff0aa367cfaae78 and mixed FP16 AdamW
  2ee480b75e8b44a8a62146dc5802dff2. Worker PIDs 86443/86654 differed from the
  backend and each other. Checkpoint/CPU generation checks passed and training loss
  decreased; models remained private and original initialization/corpus stayed intact.
- Native measured work was .4804677920 s (SGD) / .4692642090 s (AdamW), peak RSS
  64765952 / 66125824 bytes and Metal peak 41392 / 43570 bytes. Refreshed reviews
  used exactly one matching sample each, producing .6005847400 / .5865802613 s
  heuristic work estimates. Measured memory floors 81009180 / 82711743 bytes were
  below calculated reserves; required reserves stayed 268767040 / 268789568 bytes.
  The app distinguished measured results, calculated floors and future estimates.
- After app/backend restart all eighteen legacy/measured records reopened exactly;
  scoped memory/time feedback still selected the same saved observations without
  retraining. All 241 original fixture files and all 255 retained files kept their
  hashes. Evidence: /tmp/almg-corpus-peaks-native-qa/verification.json,
  sgd-before-ui.json, adamw-before-ui.json, sgd-trained-ui.json,
  adamw-trained-ui.json, sgd-feedback-ui.json, adamw-feedback-ui.json and restarted
  native captures. No external collection occurred; generated artifacts and weights
  remain outside Git.
- Validation: 630 Python tests passed with warnings as errors and Metal enabled,
  78 Flutter tests passed, analysis clean. New tests cover actual fresh-worker peaks,
  exact compatible feedback, cross-corpus/configuration/runtime/producer rejection,
  no-consent/stale-review prevention, calibrated-memory rejection before launch,
  nonce/result binding and source preservation. UI tests distinguish measured peaks,
  calculated reserves and heuristic estimates. The high-floor resource case uses
  a local fixture profile and does not change or exhaust actual host memory.
- Remaining: isolated corpus continuation/retained-partial profiling and scoped
  feedback, broader budgets/model scales, arbitrary interruption and independent
  Windows/CUDA/physical-host verification. These bounded reports do not establish
  50M–100M feasibility or general model quality. Unchanged hardware/user-action
  blockers remain open and skipped; P3-LMF-06 fresh-run cancellation also stays open.

P3-LMF-05 partial progress · isolated corpus recovery peaks and exact-source feedback · 2026-11-21:
- [ ] P3-LMF-05 remains open. App-approved original-midpoint continuation and
  retained-partial resume now execute in fresh workers. Parent and child both check
  current approval/resource bindings; nonce, actual child PID, recovery action,
  original/partial source and exact reviewed payload are checked on return. Existing
  completed/canceled lineage and source-bound cancellation receipts stay intact.
- Version-1 recovery measurements distinguish original-midpoint and partial-resume
  actions. RSS/Metal lifetime peaks include runtime/lineage overhead; module-entry
  time covers imports/admission, restore, only the approved remaining updates,
  evaluation/state saving and CPU generation. Parent launch/admission, pre-module
  startup, queue/approval waits and final publication are excluded. No uninterrupted
  retraining trajectory is executed. Shared phase samples stay separately labeled;
  old shared and measured full-training records remain readable without rewriting.
- Fresh recovery reviews select verified completed measurements matching exact
  original run/checkpoint revision, retained-partial snapshot (when present), actual
  restored update, corpus revision, configuration, runtime, execution mode and
  producer. Highest matching time plus 25% headroom provides a labeled heuristic;
  RSS/Metal sum plus 25% headroom can raise, never reduce, calculated reserves.
  Canceled observations never calibrate forecasts or memory floors. A different
  partial/update cannot inherit another source's feedback. Current calibrated
  availability is checked before launch. Zero-update cancellation can legitimately
  report zero Metal allocation while retaining valid CPU model/optimizer state.
- Native verification: rebuilt/launched ALMG and reopened all eighteen prior records
  exactly. Explicitly completed isolated midpoint recovery from update ten and
  partial recovery from update eleven for legacy FP32 SGD and mixed FP16 AdamW.
  Midpoint records e1e89976b8964bcb85857bdf24d8b67d (SGD) /
  36fafa1f54cc42bb8b2db8f7bbe7c615 (AdamW) executed only updates eleven–twenty.
  Completed partial records 71b9b3caf3574ff2a4f8ed438080d8ef /
  2ca2ce30475e455eb1692ad83b176922 executed only twelve–twenty and matched source
  weights within 1e-7 with identical CPU-generated tokens/text.
- Native unpaced work times were .3516470 / .3592591 s (SGD midpoint/partial) and
  .3936951 / .4105355 s (AdamW midpoint/partial). RSS peaks were 62816256 /
  63668224 / 63553536 / 63438848 bytes; Metal peaks 21968 / 21968 / 40754 /
  40754 bytes. Distinct workers had PIDs 6286/6360/6465/6536, separate from the
  backend. Refreshed exact-source work estimates were .4395587 / .4490739 /
  .4921189 / .5131694 s. Memory reserves stayed at their larger calculated levels:
  268761408 bytes for SGD and 268789568 for AdamW.
- Live Cancel also crossed the process boundary: local-only child pacing made
  partial updates observable; actual app cancellation retained update twelve in
  df967b8118724c8299fe9c234af6db36 (SGD) and
  dddab56d284b40ea8f64f1b0a06e0f33 (AdamW). Their private state/own CPU inference
  reopened correctly. Pacing was removed for completed measurements. Native reviews
  proved these canceled samples did not enter feedback, midpoint samples did not
  enter partial estimates, and new update-twelve partials had no inherited estimate.
- After app/backend restart all twenty-four original/measured/completed/canceled
  records and exact-source feedback reopened unchanged without retraining. All 255
  original fixture files and all 283 retained files kept their hashes. Evidence:
  /tmp/almg-corpus-recovery-peaks-native-qa/verification.json, midpoint/partial
  before/result/feedback captures, after-cancel-feedback and different-partial-
  feedback captures for SGD/AdamW, plus restarted native captures. No external
  collection occurred; generated models, optimizer states, receipts and measurements
  remain outside Git.
- Validation: 632 Python tests passed with warnings as errors and Metal enabled,
  79 Flutter tests passed, analysis clean. New tests cover actual isolated midpoint/
  partial peaks, restored-source-only estimates, canceled/zero-update handling,
  preserved source states and calibrated-memory rejection before worker creation.
  UI tests distinguish recovery estimates and measured worker reports. Native tests
  additionally verify live child cancellation and cold feedback for a different partial.
- Remaining: broader model/budget profiling depends on expanded P3-LMF-06 engine
  support; bounded corpus execution is still capped at 16384 parameters and ten/
  twenty original updates. Windows/CUDA lacks an available host; physical power/
  sleep/idle verification requires user action. These criteria stay open and skipped.
  Independent P3-LMF-06 fresh-run cancellation and arbitrary interruption recovery
  remain open; these measurements establish no 50M–100M feasibility or model quality.

P3-LMF-06 partial progress · phase-aware fresh corpus run cancellation · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh corpus training now exposes live Cancel with a
  new random token bound to the exact frozen approval/source/corpus review. The
  receipt is handled outside the GPU queue and checked between complete optimizer
  updates during both uninterrupted reference verification and recorded checkpointed
  training. No worker is killed and no original initialization or artifact is deleted.
- New version-4 canceled-run records retain the active phase, its actual model,
  FP32 optimizer state/counter, executed window/schedule logs and own CPU text. They
  separately record reference and recorded-training progress and never claim a
  completed reference comparison or quality/release acceptance. A cancellation in
  recorded training also retains the completed reference model/moments/log and any
  saved midpoint checkpoint. Cancellation before the first update retains initial
  state. Completed runs preserve their existing model/checkpoint contracts.
- Reads verify phase/counter ranges, receipt/review bindings, exact file sets and
  hashes, finite optimizer moments, original corpus/tokenizer, executed target/window/
  learning-rate traces and private CPU inference. Canceled observations cannot enter
  time/memory feedback and are rejected as ordinary midpoint-continuation sources;
  independent phase-aware fresh-partial resume remains unimplemented. The app labels
  phase progress and suppresses the inappropriate continuation action.
- Native verification found an initial HTTP-400 cancellation routing bug: a shared
  architecture guard expected the launch initialization body. Cancel now uses its
  own frozen-review architecture/source check without requiring that launch body.
  Added an API regression proving valid frozen-review cancellation bypasses the GPU
  queue while a different architecture is rejected. The failed paced attempt and
  its artifacts remain preserved separately in /tmp/almg-corpus-fresh-cancel-native-qa;
  they are documented as failure evidence, not production timing samples.
- Rebuilt/relaunched ALMG against clean local fixtures and the corrected route.
  Real app Cancel stopped FP32 SGD reference verification at update one in private
  record 11fc676ab1f54d47a4aac0a8e29245e3: reference count one, recorded training
  count zero and no midpoint. Mixed FP16 AdamW stopped recorded training at update
  twelve in f56e58d0f8aa4ba9b0124e7bcaf64d5c, retaining the completed twenty-update
  reference model/moments, actual training model/state twelve and restored midpoint
  ten. Local-only phase pacing made the short live actions observable; gradients,
  updates, receipts and persistence were real.
- Removed pacing and explicitly approved new-token runs. SGD
  9c2098234bc549908579972658c7eba7 and AdamW
  d81fbd1f70a04137962bf9ab2a0e4ef0 completed all twenty recorded updates and passed
  their original checkpoint/reference/inference checks. Old cancellation tokens did
  not affect these runs. Native resource reviews after each canceled run had no
  measured forecast, proving incomplete observations were excluded.
- After app/backend restart all twenty-eight legacy/completed/phase-canceled records,
  active/reference optimizer states, midpoint files and own CPU text reopened exactly.
  All 283 original fixture files and all 312 retained files kept their hashes.
  Evidence: /tmp/almg-corpus-fresh-cancel-native-verified/verification.json,
  sgd-canceled-ui.json, adamw-canceled-ui.json, canceled-reopened and after-cancel-
  feedback captures, completed/restarted captures, plus preserved initial failure
  diagnostics. No external collection occurred; artifacts, receipts and weights stay
  outside Git.
- Validation: final 636 Python tests passed with warnings as errors and Metal enabled;
  80 Flutter tests passed and analysis was clean. New real SGD/mixed AdamW tests
  cancel in reference, pre-midpoint and post-restore training phases, verify retained
  reference/checkpoint/state/counters, reject modified state and token/review reuse,
  preserve original files and exclude incomplete feedback. UI tests cover the active
  token and phase labeling; the API regression covers the native-discovered bug.
- Remaining: independently approved resume of phase-aware fresh canceled runs,
  arbitrary durable OS/process interruption, larger model/budget support and profiling,
  broader quality evaluation and profiled 50M–100M training. Existing continuation/
  retained-partial recovery remains available. Unchanged independent hardware/user-
  action blockers remain open and skipped; these toy runs establish no model release.

P3-LMF-06 partial progress · separately approved retained-reference resume · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh corpus runs canceled during reference
  verification now offer a separate resource review and explicit resume approval.
  The review binds the exact retained record revision/files, original initialization,
  corpus, optimizer/precision settings, phase and actual counter. It restores FP32
  weights/moments and finishes only the missing reference updates, then executes
  the original checkpointed training budget from the original fresh initialization.
  Completed/training-phase sources, changed approvals and cyclic/excessive ancestry
  are rejected. Reference re-cancellation retains a new immutable private partial;
  further reference resume requires another review, with at most sixteen ancestors.
- Records distinguish carried reference updates from newly executed updates and
  preserve the carried reference log. Separate isolated-worker resume measurements
  never calibrate full fresh-run time/memory feedback. Existing midpoint continuation,
  cancellation receipts, completed/canceled histories and CPU generation remain valid.
- Native verification on this Mac used the rebuilt ALMG app and offline fixture
  backend at port 28913. Live SGD resume carried reference update 1, canceled again
  at update 2, then completed using 18 new reference updates plus the original 20
  recorded training updates. A live mixed FP16 AdamW reference cancellation at
  update 2 likewise resumed with 18 new reference updates and 20 recorded updates.
  Both completed models had zero checkpoint weight/moment difference, decreasing
  full-split training loss and matching reloaded tokenizer-backed CPU generation.
  Worker timings/peaks and carried/executed counters were observed in native results.
- After app/backend restart, all 20 corpus optimizer records and three representative
  legacy completed/canceled/chained continuations reopened exactly in native history;
  backend readers verified all 36 corpus/continuation records. All 358 retained files
  stayed byte-identical, including the original 312 and the first successful pass's
  artifacts. Evidence: /tmp/almg-corpus-reference-resume-native-qa/verification.json,
  native.log, restart.log and captured reviews/results. Nothing was collected externally.
- Validation: 638 Python tests passed with Metal enabled and warnings as errors;
  the final lineage/import/scope changes passed all 23 corpus tests. All 81 Flutter
  tests passed; final analysis was clean. Tests verify actual executed update indices,
  FP32 SGD/mixed AdamW state, re-cancellation, immutable parents, approval/cycle
  rejection, isolated process identity and exclusion from fresh-run forecasts.
- Remaining: independently approved resume after cancellation during recorded
  checkpointed training, arbitrary durable OS/process interruption, broader model/
  budget support and profiling, quality evaluation and profiled 50M–100M training.
  P3-LMF-01 remains complete for its recorded architecture scope. Unchanged independent
  hardware/user-action blockers remain open and skipped. This verifies bounded
  private optimizer recovery, with no language-quality or release acceptance claim.

P3-LMF-06 partial progress · separately approved recorded-training resume · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh corpus runs canceled during recorded training
  now offer a separate phase-specific resource review and explicit resume approval.
  The review binds the exact retained record/revision/files, original initialization,
  corpus, optimizer/precision settings and actual training counter. Resume reuses the
  saved completed reference and its FP32 optimizer state without reference retraining,
  restores the active FP32 training model/moments and executes only remaining original
  updates. It preserves carried logs and separately records carried/executed work.
- Before the midpoint, resumed training reaches and restores the original midpoint
  checkpoint. At/after the midpoint, its saved model/moments are preserved in a new
  checkpoint bound to the new approval, while training resumes from the actual later
  counter. Completed and wrong-phase sources, stale approvals, changed ancestry and
  cyclic/excessive lineage are rejected. Re-cancellation saves another private partial;
  each further resume requires another review, with at most sixteen ancestors across
  reference-to-training recovery. All source files remain immutable.
- Separate isolated recorded-training resume time/peak measurements are persisted
  with exact worker identity and approval binding. Completed/canceled resume samples
  cannot calibrate full fresh-run forecasts. Existing saved reference resumes and
  ordinary midpoint continuations remain readable and functional.
- Native verification used the rebuilt local ALMG app and offline fixture backend at
  port 28914. SGD fresh training canceled at update 2, resumed and canceled at 3, then
  completed using 17 remaining updates. Mixed FP16 AdamW restored the existing update-12
  state, canceled at 13, then completed with seven remaining updates. Both executed
  zero reference optimizer updates, had zero final weight/moment difference from the
  retained completed reference, decreasing full-split training loss and matching
  reloaded tokenizer-backed CPU generation. Both outputs also completed independently
  approved midpoint continuation from update 10 to 20 in the native app.
- After app/backend restart, all latest 20 corpus optimizer records and both new
  midpoint continuations reopened exactly in native histories; backend readers
  verified all 43 retained corpus/continuation records, including older records outside
  the twenty-entry UI history. All 404 retained files, including all original 358,
  remained byte-identical. Evidence: /tmp/almg-corpus-training-resume-native-qa/
  verification.json, native.log, midpoint.log, restart.log and captured reviews/results.
  No external collection occurred; models, receipts and QA outputs stay outside Git.
- Validation: 640 Python tests passed with warnings as errors and Metal enabled;
  all 82 Flutter tests passed and analysis was clean. Real SGD/mixed AdamW tests
  restore source training updates 0, 1, 10 and 11; re-cancel and finish; assert the exact
  executed update indices with no reference replay, preserved midpoint/model/moment
  bytes, immutable ancestors, stale approval/cycle rejection, isolated worker identity,
  zero-update cancellation and exclusion from fresh-run calibration.
- Remaining: arbitrary durable OS/process interruption recovery, exact resumed-work
  calibration, broader model/budget support and profiling, quality evaluation and
  profiled 50M–100M training. P3-LMF-01 remains complete for its recorded architecture
  scope. Unchanged independent hardware/user-action blockers remain open and skipped;
  this bounded recovery slice establishes no language-quality or release acceptance.

P3-LMF-05 partial progress · exact-source fresh corpus phase-resume feedback · 2026-11-21:
- [ ] P3-LMF-05 remains open. Separately approved fresh corpus reference and recorded-
  training resumes now derive resource reviews from compatible completed isolated
  observations. Matching requires the exact retained source/revision/files and actual
  counter, resume phase, corpus, optimizer/precision/model configuration, runtime,
  producer and execution policy. Canceled/incomplete, shared-process, malformed,
  changed-source/config/runtime/producer and other-phase samples are excluded.
- Reviews show measured RSS/Metal peaks separately from a calculated memory floor
  and heuristic remaining-work estimate. Time uses the maximum compatible observed
  worker time plus 25% headroom. The memory floor uses maximum compatible RSS plus
  maximum Metal peak with 25% headroom; it can only raise existing conservative
  reserves. Raised floors that exceed current resources block before worker launch.
  Samples come from the latest twenty verified corpus runs. These are exact-source
  workflow estimates, not total wall-time bounds or larger-model predictions; parent
  launch/admission and queue/approval waits remain excluded. Full fresh-run forecasts
  remain separate and cannot consume either phase-resume profile.
- Native verification used the rebuilt ALMG app and offline fixture backend on port
  28915. Mixed FP16 AdamW reference resume from update 2 and recorded-training resume
  from update 13 both began without estimates. Live cancellation at reference update
  3 / training update 14 produced no estimate, and reviewing each new retained partial
  also had no compatible forecast. Two unpaced completed resumes per original source
  produced sample counts 1 then 2 with exact observed-time/max-peak calculations.
  Final two-sample estimates were 0.899 s for reference resume and 0.889 s for recorded-
  training resume; calculated measured-peak floors were 85,415,103 and 86,664,383 bytes.
  Existing reserves never decreased. Completed models passed checkpoint/CPU checks.
- After app/backend restart, the latest twenty saved corpus records reopened exactly
  in native history, and both original-source reviews retained their exact two-sample
  estimates/floors. Backend readers verified all 49 corpus/continuation records. All
  445 retained files, including all original 404, stayed byte-identical. Evidence:
  /tmp/almg-corpus-phase-feedback-native-qa/verification.json, native.log, restart.log,
  and captured cold/canceled/different-partial/completed/feedback/restarted reviews.
  No external collection occurred; generated QA artifacts and weights stay outside Git.
- Validation: 642 Python tests passed with warnings as errors and Metal enabled;
  all 83 Flutter tests passed and analysis was clean. New tests cover exact-source/
  phase/counter matching, incompatible and invalid observations, conservative two-
  sample maxima, real isolated phase execution, canceled/zero-update exclusion,
  same-counter different partials, original-file preservation and calibrated-memory
  rejection before process creation. UI tests distinguish estimates from measurements.
- Remaining: broader model/budget profiling depends on expanded P3-LMF-06 engine
  support beyond the current 16384-parameter and ten/twenty-update limits. Other
  source/configuration/phase profiles require their own completed compatible samples.
  Windows/CUDA has no available host; physical power/sleep/idle checks require user
  action. These unchanged blockers remain open and skipped. Arbitrary durable process/
  OS interruption recovery and broader quality/50M–100M acceptance remain in P3-LMF-06.

P3-LMF-06 partial progress · reviewed forty-update corpus budget · 2026-11-21:
- [ ] P3-LMF-06 remains open. Reviewed corpus training now offers forty original
  optimizer updates through explicit version-6 settings and a new resource review.
  Version-6 accepts exactly forty updates, retains the original warmup/cosine,
  clipping, batch/microbatch and FP32/mixed precision contracts, and checkpoints at
  update twenty. Version-5 ten/twenty-update settings keep their original meaning.
  Synthetic fixture admission rejects version-6 before loading weights; this expanded
  budget is available through the separately confirmed reviewed-corpus workflow only.
- Full comparison trajectories, optimizer/scheduler counters, saved histories,
  reference/recorded-training partial recovery and independent midpoint continuation
  all use the approved forty-update budget. Resumes keep their original budget and
  actual counter; the new setting cannot silently extend an existing twenty-update
  run. Feasibility profiles/forecasts remain configuration-specific, and forty-update
  observations cannot calibrate twenty-update reviews. Conservative reserves remain.
- Native verification used the rebuilt ALMG app and offline fixture backend on port
  28916 with the existing 704-parameter, eight-token reviewed corpus fixture, two
  effective rows and two token-weighted microbatches. FP32 SGD completed both forty-
  update comparison trajectories, saved/restored update twenty and generated text
  from its reloaded private model. Mixed FP16 AdamW completed its forty-update
  reference, canceled recorded training at update 21 with the update-20 checkpoint,
  then resumed exactly nineteen training updates with zero reference retraining.
  Both completed results had zero checkpoint weight/moment difference and decreasing
  full-split training loss. Each also completed separately approved midpoint
  continuation from update twenty to forty with zero reference weight difference.
- The native forty-update SGD review acquired one compatible measured sample; the
  twenty-update review stayed cold. After app/backend restart, the latest twenty
  saved corpus records and both new midpoint continuations reopened exactly, and
  forty-update feedback remained available. Backend readers verified all 54 corpus/
  continuation records, including older twenty-update records outside UI history.
  All 477 retained files, including the original 445, stayed byte-identical. Evidence:
  /tmp/almg-corpus-forty-native-qa/verification.json, native.log, restart.log and captured
  reviews/completed/canceled/resumed/midpoint/history/feedback results. No external
  collection occurred; generated models, receipts and QA files remain outside Git.
- Validation: 644 Python tests passed with warnings as errors and Metal enabled;
  all 84 Flutter tests passed and analysis was clean. New tests reject wrong-version,
  unsupported/noninteger budgets and synthetic version-6 admission; exercise actual
  isolated SGD/mixed AdamW forty-update optimization, final cosine rate, twenty-step
  checkpoints, independent continuation, both fresh-run phase resumes, immutable
  ancestors, and budget-specific forecasts. UI tests require a fresh approval after
  selecting forty updates and verify version-6/forty-update submission.
- Remaining: arbitrary durable OS/process interruption recovery, model/sequence/
  batch expansion beyond the current bounded engine, broader budget/resource
  profiling and quality evaluation, and profiled 50M–100M training. Forty updates
  on a tiny fixture do not establish language quality or production-scale feasibility.
  Unchanged independent hardware/user-action blockers remain open and skipped;
  P3-LMF-01 remains complete for its recorded architecture scope.

P3-LMF-06 partial progress · durable fresh-worker midpoint recovery · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh isolated corpus workers now publish an immutable
  version-5 interruption-checkpoint record after the ordinary midpoint checkpoint is
  saved and before post-midpoint training begins. It retains the midpoint FP32 model,
  optimizer/scheduler counter, tokenizer, training log, complete reference model/moments
  and reference log, frozen approval/source bindings and originating worker/run IDs.
  Data files are flushed before the manifest is atomically published last; directory
  entries are flushed afterward. Partial/failed publication is not discoverable, and
  original pending/completed/canceled run files are preserved. Extra disk and memory
  reserves are included in resource admission. Legacy result formats stay unchanged.
- Added native “Saved interruption checkpoints” discovery. A checkpoint is offered
  only after its originating POSIX worker has stopped and no originating terminal
  record exists; active and completed/canceled origins are excluded. Non-POSIX hosts
  do not perform process probes. New resource review and explicit approval restore
  the saved midpoint and execute the original remaining updates in a new private run,
  reusing the complete reference without retraining. Later uncheckpointed work is
  replayed, and the UI states that scope. Checkpoints are distinct retained artifacts,
  with no fabricated cancellation receipts or completed-training/release claim.
- Native verification used the rebuilt ALMG app and offline fixture backend on port
  28917. Two explicitly approved forty-update fixture workers (FP32 SGD and mixed FP16
  AdamW, 704 parameters, two effective rows/two microbatches) were terminated with
  SIGKILL only after their update-20 snapshots had published and post-midpoint work
  was active. The test verified each owned child PID, parent backend and command before
  termination. The app reported the expected worker failure and exposed both intact
  midpoint snapshots. An initial test selector matched explanatory text instead of
  the button; the exact-label selector was corrected, preserving the first snapshot
  and diagnostics rather than rerunning or discarding its artifacts.
- After app/backend restart, both saved checkpoints required new resource review/
  confirmation and completed exactly twenty remaining training updates to update 40,
  with zero reference optimizer updates, zero final weight/moment error against the
  retained reference and matching reloaded CPU generation. Each recovered output also
  completed independently approved midpoint continuation from update 20 to 40 with
  zero reference weight difference. No cancellation receipt was created for either
  interrupted source. Recovery creates separate models and leaves its source immutable.
- A final app/backend restart reopened the latest twenty ordinary corpus records,
  both interruption sources and both recovered midpoint continuations exactly.
  Backend readers verified all 60 corpus/checkpoint/continuation records. All 523
  retained files remained byte-identical, including all original 477 and all 503 files
  present after interruption. Evidence: /tmp/almg-corpus-interruption-native-qa/
  verification.json, interrupt-first-selector-attempt.log, selector-issue.txt,
  interrupt-corrected.log, expected-interruption UI captures, recover.log, restart.log
  and raw checkpoint/review/recovered/continuation captures. No external collection
  occurred; generated checkpoints, models, receipts and QA files remain outside Git.
- Validation: final 648 Python tests passed with warnings as errors and Metal enabled;
  all 85 Flutter tests passed and analysis was clean. Real worker-termination tests
  verify both optimizers, active/terminal exclusion, explicit confirmation, original
  bytes, checkpoint integrity, no cancellation receipt and exact recovered state.
  Tests also cover failed flush publication without a manifest and the non-POSIX
  no-signal guard. UI tests expose the saved midpoint with separate approval and
  exclude the ordinary completed-run continuation action for an incomplete checkpoint.
- Remaining: recovery before the fresh recorded-training midpoint, newer-than-midpoint
  periodic checkpoints, arbitrary interruption points/resumed-worker lifecycle,
  physical OS/power-loss verification, larger model/sequence/batch/budget support,
  profiling and quality/50M–100M acceptance. This verifies bounded fresh-worker process
  interruption after successful midpoint publication only. Unchanged independent
  hardware/user-action blockers remain open and skipped; P3-LMF-01 remains complete
  for its recorded architecture scope.

P3-LMF-06 partial progress · training-start interruption recovery and latest points · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh isolated corpus workers now publish a flushed,
  immutable version-6 training-start interruption record immediately after completing
  the reference trajectory and before the first recorded training update. It retains
  the complete reference model/moments/log, initial FP32 training model, empty optimizer
  state at counter zero, tokenizer and frozen source/approval bindings. Recovery can
  replay the original recorded-training budget without repeating reference optimization.
  Version-5 midpoint records remain supported. Resource admission now reserves disk
  for both points; partial publication, active origins and terminal origins stay excluded.
- Discovery selects one latest complete point per originating run, preferring the
  highest saved training counter even if wall-clock timestamps regress. It verifies
  matching originating worker and approval metadata and rejects conflicts. An earlier
  training-start record is preserved but hidden when the midpoint is available.
  The UI distinguishes training-start/midpoint state, discloses replay of uncheckpointed
  work and requires separate resource review and explicit recovery confirmation.
- Native verification used the rebuilt local ALMG app and offline fixture backend
  on port 28918 with the existing 704-parameter, eight-token, two-row/two-microbatch
  forty-update corpus fixture. Owned FP32 SGD and mixed FP16 AdamW workers were
  terminated with SIGKILL during the first half of recorded training, after the
  training-start record had published. Both exposed update-zero checkpoints with a
  complete update-40 reference. A third SGD worker was terminated post-midpoint;
  native discovery selected update 20 and omitted its older update-zero record while
  preserving that record's files. Each child PID/parent/command was verified before
  termination; no cancellation receipt was created for any interrupted source.
- After app/backend restart, new resource reviews restored the two zero-counter
  sources and completed forty training updates each, with zero reference optimizer
  updates. The selected midpoint completed twenty remaining updates. All three models
  had zero final weight/moment error against their retained references and matching
  reloaded CPU generation, and all three completed independently approved update-20
  to update-40 midpoint continuation with zero reference weight difference. A native
  test lookup initially ran before a modal-close transition finished; a bounded exact-
  button wait corrected the driver and reused the already completed SGD recovery.
- A final app/backend restart reopened the latest twenty ordinary records, three
  selected interruption points and three recovered continuations exactly. Latest-point
  selection still omitted the older zero-counter record. Backend readers verified
  all 70 corpus/checkpoint/continuation records, including all retained generations.
  All 585 retained files stayed byte-identical, including the original 523 and all
  555 files present after interruption. Evidence: /tmp/almg-corpus-training-start-native-qa/
  verification.json, interrupt.log, recover-first-transition-attempt.log,
  transition-issue.txt, recover-corrected.log, restart.log and raw selected/review/
  recovered/continuation captures. No external collection occurred; generated models,
  snapshots and QA files remain outside Git.
- Validation: 649 Python tests passed with warnings as errors and Metal enabled;
  all 85 Flutter tests passed and analysis was clean. Real worker-termination tests
  cover both optimizers before/after midpoint, zero/midpoint restore counters, exact
  final state, source preservation and distinct receipt-free interruption artifacts.
  Tests additionally cover latest-counter selection under clock regression, conflicting
  origin/approval rejection, terminal/active exclusion, failed publication and the
  non-POSIX no-signal guard. UI tests cover both zero and midpoint recovery approval.
- Remaining: reference-phase interruption before training-start publication, periodic
  newer-than-midpoint checkpoints, resumed-worker lifecycle and arbitrary interruption
  points, physical OS/power-loss verification, larger model/sequence/batch/budget
  support, profiling and quality/50M–100M acceptance. This slice verifies fresh-worker
  process recovery from successfully published training-start/midpoint points only.
  Unchanged independent hardware/user-action blockers remain open and skipped;
  P3-LMF-01 remains complete for its recorded architecture scope.

P3-LMF-06 partial progress · reference-start interruption recovery and phase ordering · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh isolated corpus workers now publish an immutable
  version-7 reference-start checkpoint after initial source/resource/precision checks
  and before reference optimization begins. It retains initial FP32 weights, empty
  optimizer state and reference counter zero, tokenizer, frozen approval/input bindings
  and originating worker/run IDs. Data/manifest publication uses the existing flushed,
  manifest-last protocol. Separate reference-recovery review and explicit confirmation
  replay the remaining reference trajectory and original recorded-training budget.
  Later uncheckpointed reference work is replayed; no intermediate progress is implied.
- Version-5 midpoint and version-6 training-start records remain readable. Admission
  reserves disk for all three durable points. Discovery prefers the advanced phase
  (recorded training over reference verification), then its highest counter, before
  considering timestamps. Thus a completed reference's training-start state wins over
  reference-start even when both counters are zero or clocks regress. Conflicting
  origin/approval bindings are rejected; older valid generations remain immutable but
  are omitted from the latest-point list. Active and terminal origins stay excluded.
  The UI identifies reference-start state and routes it to reference recovery only.
- Native verification used the rebuilt ALMG app and offline fixture backend on port
  28919 with the existing 704-parameter, eight-token, two-row/two-microbatch forty-update
  fixture. Owned FP32 SGD and mixed FP16 AdamW workers were terminated with SIGKILL
  during reference optimization after reference-start publication. Both exposed saved
  reference counter zero, with no recorded training or fabricated cancellation receipt.
  Two additional SGD interruptions during recorded training exposed training-start
  counter zero and midpoint counter twenty. Native discovery omitted their earlier
  phase/counter generations while retaining all seven newly published snapshot records.
  Every child PID, parent backend and command was checked before termination.
- After app/backend restart, phase-specific resource reviews required new confirmation.
  Each reference-start source executed forty reference updates plus forty recorded
  updates; training-start reused its full reference and executed forty training updates,
  and midpoint reused its full reference and executed twenty remaining updates. All four
  completed models had zero final weight/moment error against their reference trajectories
  and matching reloaded CPU generation. Each also completed independently approved
  update-20 to update-40 midpoint continuation with zero reference weight difference.
- A final app/backend restart reopened the latest twenty ordinary records, four selected
  interruption points and four continuations exactly, preserving phase/counter precedence.
  Backend readers verified all 85 corpus/checkpoint/continuation records. All 667 retained
  files stayed byte-identical, including the original 585 and all 627 files present after
  interruption. Evidence: /tmp/almg-corpus-reference-start-native-qa/verification.json,
  interrupt.log, expected-worker-failure UI captures, recover.log, restart.log and raw
  selected/review/recovered/continuation captures. No external collection occurred;
  generated models, snapshots and QA files remain outside Git.
- Validation: 649 Python tests passed with warnings as errors and Metal enabled; all
  86 Flutter tests passed and analysis was clean. Actual worker-termination tests now
  cover reference-start, training-start and midpoint recovery for both optimizers,
  exact replay counts, ownership/approval gates, source bytes, artifact integrity and
  receipt-free interruption state. Phase ordering is tested under clock regression,
  alongside conflicting-origin rejection, incomplete publication and non-POSIX guards.
  UI tests require separate reference approval and exclude training/completed-run actions
  for reference-start sources.
- Remaining: interruption during admission/initial checks or before successful checkpoint
  publication, periodic reference/training checkpoints that retain newer progress,
  resumed-worker lifecycle/arbitrary interruption points, physical OS/power-loss
  verification, larger model/sequence/batch/budget support, profiling and quality/
  50M–100M acceptance. This verifies fresh-worker process recovery from the three published
  start/midpoint points only. Unchanged independent hardware/user-action blockers remain
  open and skipped; P3-LMF-01 remains complete for its recorded architecture scope.

P3-LMF-06 partial progress · durable reference-midpoint recovery · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh isolated corpus workers now publish a version-8
  reference-midpoint checkpoint at half the approved reference budget, retaining the
  active FP32 weights, optimizer moments/counter, reference update log, tokenizer and
  frozen source/approval/worker bindings. Publication uses the existing flushed,
  manifest-last protocol. Separate reference-recovery review and explicit confirmation
  restore that state and execute only the remaining reference updates, followed by
  the original recorded-training trajectory. Later uncheckpointed work is replayed.
- Existing version-5 training-midpoint, version-6 training-start and version-7
  reference-start records remain readable. Admission reserves disk for four durable
  points. Discovery prefers training over reference phase, then the largest saved
  counter, preserving older immutable generations. The native UI labels reference
  midpoint state and offers reference recovery rather than recorded-training recovery
  or completed-model continuation actions.
- Native verification used the rebuilt ALMG app and offline fixture backend on port
  28920 with the existing 704-parameter, eight-token, two-row/two-microbatch forty-update
  corpus fixture. Owned FP32 SGD and mixed FP16 AdamW workers were terminated after
  reference update 20 was published. Discovery selected reference counter 20 rather
  than zero. Additional SGD interruptions selected training-start zero and training
  midpoint 20, ahead of both reference generations. Every child PID, parent backend
  and command was checked before termination. All eleven new snapshots were retained;
  no cancellation receipt or completed originating run was fabricated.
- After app/backend restart, each recovery required its phase-specific resource review
  and new confirmation. Both reference-midpoint sources carried 20 reference updates,
  executed 20 remaining reference updates and completed 40 recorded updates. Training
  start reused its full reference and executed 40 training updates; training midpoint
  executed 20. All four completed models matched reference weights and optimizer state
  exactly and passed reloaded CPU generation checks. Each completed a separately
  approved update-20 to update-40 continuation with zero reference weight difference.
- A final app/backend restart reopened twenty ordinary records, four selected
  interruption points and four continuations exactly. Backend readers verified all
  104 corpus/checkpoint/continuation records. All 765 retained files stayed byte-identical,
  including the original 667 and the 725 present after interruption. Evidence:
  /tmp/almg-corpus-reference-midpoint-native-qa/verification.json, interrupt.log,
  recover.log, restart.log and native selected/review/recovered/continuation captures.
  The verification driver initially reached the relaunched app before its accessibility
  window was ready; the preserved startup-transition log records that harness timing
  failure. Recovery began after the window became ready and then passed.
- Validation: 649 Python tests passed with Metal enabled and warnings as errors;
  87 Flutter tests passed and analysis was clean. Actual owned-worker termination
  tests cover both optimizers at reference start/midpoint and training start/midpoint,
  exact replay counts, approval/liveness gates, unchanged source bytes and corrupt
  artifact rejection. UI coverage requires separate approval for both reference points.
- Remaining: checkpoints beyond these four published points, interruption during
  admission/initial checks or publication, resumed-worker lifecycle, physical OS/power
  loss, broader model/sequence/batch/budget support, profiling and language-quality/
  50M–100M acceptance. Independent hardware/user-action blockers remain open and skipped;
  P3-LMF-01 remains complete for its recorded architecture scope. No external collection
  occurred; generated artifacts, weights and unrelated user edits are excluded from Git.

P3-LMF-06 partial progress · quarter-budget reference recovery points · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh isolated corpus runs now retain additional
  reference checkpoints at floor(budget/4) and floor(3*budget/4), alongside reference
  start/midpoint and recorded-training start/midpoint. For forty updates these add
  reference counters ten and thirty. Version-9 immutable records bind the active FP32
  weights, optimizer moments/scheduler counter, reference log, tokenizer and exact
  frozen source/approval/worker ownership. Existing flushed, manifest-last publication
  and separate reference-recovery approval apply. Admission reserves six checkpoints.
- Readers retain version-5 through version-8 compatibility. Discovery still prefers
  the advanced phase and then its highest saved counter, preserving older generations.
  The native UI labels saved reference progress and requires a new reference review
  and confirmation. These points retain only completed published work; updates after
  the latest point must replay. Resumed workers do not yet publish new recovery points.
- Native verification used rebuilt ALMG with the offline 704-parameter corpus fixture
  on port 28921: forty updates, sequence eight, two rows and two microbatches. Owned
  FP32 SGD and mixed FP16 AdamW workers were terminated after reference checkpoint 30
  was published. Discovery selected counter thirty and omitted earlier 0/10/20 points.
  Additional SGD interruptions during recorded training selected training start zero
  and training midpoint twenty ahead of all reference points. Every child PID, command
  and parent backend was checked before termination. All nineteen new snapshot records
  were retained; no completed origin or cancellation receipt was fabricated.
- After app/backend restart, each selected point required phase-specific resource review
  and new confirmation. Reference recovery carried thirty updates, executed ten remaining
  reference updates and completed forty recorded updates for both optimizers. Training
  start executed forty training updates; training midpoint executed twenty; both reused
  their completed reference. All four final models matched reference weights/moments
  exactly and passed reloaded CPU generation checks. Independently approved update-20
  to update-40 continuation also matched exactly for each recovered model.
- A final app/backend restart reopened twenty ordinary records, four selected interruption
  checkpoints and four continuations exactly. Readers verified all 131 corpus, interruption
  and continuation records. All 895 retained files remained byte-identical, including
  the original 765 and the 855 present after interruption. Evidence:
  /tmp/almg-corpus-reference-progress-native-qa/verification.json, interrupt.log,
  recover.log, restart.log, restart-remaining.log and raw native captures. One final
  capture briefly had no accessible app window; the expected existing record became
  readable again. The remaining driver resumed from that record, preserved successful
  captures and the failure diagnostics, and did not rerun training or recoveries.
- Validation: 649 Python tests passed with Metal enabled and warnings as errors;
  88 Flutter tests passed and analysis was clean. Actual worker-termination coverage
  now exercises reference 0/10/20/30 and training 0/20 for both optimizers, separate
  approval, exact remaining update counts, liveness/integrity gates and source immutability.
- Remaining: newer recorded-training checkpoints, arbitrary interruption/admission/
  publication points, resumed-worker lifecycle, physical OS/power-loss verification,
  broader model/sequence/batch/budget support, profiling and language-quality/50M–100M
  acceptance. Independent hardware/user-action blockers stay open and skipped.
  P3-LMF-01 remains complete for its documented architecture scope. No external
  collection occurred; generated artifacts, weights and unrelated edits are outside Git.

P3-LMF-06 partial progress · quarter-budget recorded-training recovery · 2026-11-21:
- [ ] P3-LMF-06 remains open. Fresh isolated corpus runs now retain recorded-training
  checkpoints at floor(budget/4) and floor(3*budget/4), in addition to their existing
  start/midpoint and four reference points. Forty-update runs add training counters
  ten and thirty. Version-10 immutable records retain active FP32 weights/moments,
  optimizer/scheduler counter, full reference artifacts/log, recorded update prefix,
  tokenizer, frozen approval/source and originating worker ownership. Publication uses
  the existing flushed, manifest-last protocol. Admission reserves eight checkpoints.
- Before midpoint, the retained point has no midpoint checkpoint. Separately approved
  recovery finishes to the original midpoint, saves/restores it and completes the budget.
  After midpoint, publication copies the already verified midpoint; recovery rebinds that
  checkpoint to its new approval while continuing from the later active state/counter.
  It does not reset the active state to midpoint. Both paths reuse the completed reference.
  Existing version-5 through version-9 records remain readable. Native discovery selects
  the highest recorded-training counter, ahead of earlier training/reference generations.
- Native verification used rebuilt ALMG and offline fixture backend port 28922 with the
  704-parameter, eight-token, two-row/two-microbatch forty-update corpus. Owned FP32 SGD
  and mixed FP16 AdamW workers were terminated after training checkpoint ten or thirty
  was published, giving four actual interruption cases. Each child PID, command and
  parent backend was checked first. Discovery exposed the latest training counter and
  omitted older generations while retaining all twenty-eight new snapshot records.
  No originating completed result or cancellation receipt was fabricated.
- After app/backend restart, all four required recorded-training resource review and
  new confirmation. Counter-ten recovery executed thirty remaining training updates;
  counter-thirty executed ten; all executed zero reference updates and retained the full
  reference. Final weights/moments matched exactly, with restored optimizer/scheduler
  counters and reloaded CPU generation. Each recovered model also completed an independently
  approved update-20 to update-40 continuation with zero reference weight difference.
- A final app/backend restart reopened twenty ordinary records, four selected interruption
  checkpoints and four continuations exactly. Backend readers verified all 167 saved
  corpus/interruption/continuation records. All 1,091 retained files stayed byte-identical,
  including the original 895 and the 1,051 present after interruption. Evidence:
  /tmp/almg-corpus-training-progress-native-qa/verification.json, interrupt.log,
  recover.log, restart.log, restart-remaining.log, restart-final.log and raw native
  captures. A final history
  selection stalled while ALMG was behind another window; raising its own window
  restored history access. Diagnostic clicks had queued extra history dialogs; these
  were dismissed before the remaining checks resumed from saved captures.
  Initial selected-record captures
  needed an accessibility-tree refresh; the temporary capture helper now performs it
  before record reads. Its prior version and diagnostics are preserved outside Git.
- Validation: 649 Python tests passed with Metal enabled and warnings as errors;
  88 Flutter tests passed and analysis was clean. Actual worker-termination coverage
  exercises reference 0/10/20/30 and training 0/10/20/30 for both optimizers, correct
  snapshot versions and counts, separate approval/liveness gates, exact remaining
  updates, lineage, artifact integrity and immutable source bytes. UI coverage checks
  both training progress points and requires separate recovery approval.
- Remaining: arbitrary interruption/admission/publication points, resumed-worker lifecycle,
  physical OS/power-loss verification, broader model/sequence/batch/budget support,
  profiling and language-quality/50M–100M acceptance. These eight published points do
  not establish arbitrary periodic or physical power-loss recovery. Independent hardware/
  user-action blockers remain open and skipped. P3-LMF-01 remains complete for its recorded
  architecture scope. No external collection occurred; generated artifacts, downloaded
  weights and unrelated user edits remain excluded from Git.

P3-LMF-06 partial progress · interrupted recorded-training recovery workers · 2026-11-21:
- [ ] P3-LMF-06 remains open. Separately approved, isolated recorded-training recovery
  workers now retain their own immutable version-11 checkpoints. They publish the
  restored entry state and later original quarter/midpoint training points. Each binds
  the current approval, immediate retained parent, ancestry depth, carried/new update
  counts, active FP32 weights/moments/scheduler, completed reference and tokenizer.
  Midpoint artifacts are saved or rebound before publication when applicable. The
  existing flushed, manifest-last publication and per-origin latest-point selection apply.
- Version-11 validation requires recorded-training recovery ancestry and permits its
  entry counter or original quarter/midpoint counters. Reopening a stopped recovery's
  point requires another resource review and explicit confirmation, checks originating
  worker liveness/terminal state, and preserves the existing sixteen-ancestor bound.
  The reference-file lineage check now covers interrupted recovery snapshots as well
  as canceled runs. Legacy version-5 through version-10 snapshots remain readable.
  Reference-recovery workers still do not publish their own new recovery points.
- Native verification used rebuilt ALMG with offline fixture backend port 28923 and
  the existing 704-parameter, sequence-eight, two-row/two-microbatch forty-update corpus.
  For both FP32 SGD and mixed FP16 AdamW, approved recovery from training ten was
  interrupted after its own training-twenty point; recovery from training thirty was
  interrupted after saving its restored thirty point. All four child PIDs, commands
  and backend parents were checked before SIGKILL. Discovery exposed each failed
  recovery's latest point with its own approval/parent/ownership, while retaining all
  six new snapshots. No completed originating run or cancellation receipt was fabricated.
- After app/backend restart, new phase-specific reviews/confirmations recovered all four
  points. Training-twenty sources executed twenty remaining training updates; training-
  thirty sources executed ten; all reused their full reference with zero reference
  updates. Completed results had ancestry depth two, exact restored optimizer/scheduler
  counters, zero final reference weight/moment error and matching reloaded CPU generation.
  Every recovered model completed separately approved midpoint-20 to update-40 continuation
  with zero reference weight difference. Successful recovery workers also retained their
  own published points; their terminal result correctly excluded those from discovery.
- A final app/backend restart reopened twenty ordinary records, four failed-recovery
  checkpoints and four continuations exactly. Readers verified all 187 corpus, interruption
  and continuation records. All 1,247 retained files stayed byte-identical, including
  the original 1,091 and the 1,153 present after interruption. Evidence:
  /tmp/almg-corpus-resumed-training-native-qa/verification.json, interrupt.log,
  recover.log, restart.log and raw native captures. Temporary accessibility helpers now
  raise ALMG's own window before reading/clicking it, addressing the prior occlusion issue;
  their previous versions remain preserved outside Git.
- Validation: 650 Python tests passed with Metal enabled and warnings as errors;
  89 Flutter tests passed and analysis was clean. New real-worker coverage interrupts
  approved training recovery before/after midpoint for both optimizers, rejects active
  owners and missing reapproval, checks parent/state/counters/depth and receipt-free
  snapshots, then recovers to an exact completed result without changing any retained file.
  UI coverage labels resumed-worker state and requires another recorded-training approval.
- Remaining: reference-recovery worker durability, arbitrary interruption/admission/
  publication points, physical OS/power-loss verification, broader model/sequence/batch/
  budget support, profiling and language-quality/50M–100M acceptance. This validates
  process interruption for recorded-training recovery only, not general OS recovery.
  Independent hardware/user-action blockers remain open and skipped; P3-LMF-01 remains
  complete for its recorded architecture scope. No external collection occurred;
  generated artifacts, weights and unrelated user edits are excluded from Git.

P3-LMF-06 partial progress · interrupted reference-recovery workers · 2026-11-21:
- [ ] P3-LMF-06 remains open. Separately approved isolated reference-recovery workers
  now publish their restored entry state and later original reference quarter/midpoint
  checkpoints. Version-12 immutable records retain active FP32 weights/moments/scheduler,
  the full carried/new reference log, tokenizer, current approval, immediate retained
  parent, ancestry depth and originating worker ownership. Recorded training has not
  started at these points. Publication uses the existing flushed, manifest-last protocol.
- Version-12 validation requires reference-recovery ancestry, accepts its entry counter
  or original reference quarter/midpoint points, excludes recorded-training bindings,
  and retains liveness/terminal checks and the existing sixteen-ancestor limit. These
  snapshots route only to a new reference resource review and explicit confirmation.
  Legacy version-5 through version-11 records remain readable. Fresh reference start
  and progress publication uses the same helper without changing its prior formats.
- Native verification used rebuilt ALMG and offline fixture backend port 28924 with the
  existing 704-parameter, sequence-eight, two-row/two-microbatch forty-update corpus.
  For both FP32 SGD and mixed FP16 AdamW, recovery from legacy reference-start zero was
  interrupted after its own reference-twenty point, and recovery from reference thirty
  was interrupted after saving its own restored thirty point. All four child PIDs,
  commands and backend parents were checked before SIGKILL. Discovery selected each
  failed recovery's latest point, retained all eight new snapshots and omitted earlier
  generations for that worker. No terminal origin or cancellation receipt was fabricated.
- After app/backend restart, all four required a second reference review and confirmation.
  Saved reference twenty executed twenty remaining reference updates; saved thirty
  executed ten; each then performed the original forty recorded-training updates.
  Completed results had reference ancestry depth two, correct carried/new counters,
  zero final reference weight/moment error and matching reloaded CPU generation. Each
  also completed independently approved midpoint-20 to update-40 continuation with zero
  reference weight difference. Successful recovery origins were excluded from interruption
  discovery after their terminal records, while their snapshots remained immutable.
- A final app/backend restart reopened twenty ordinary records, four failed reference-
  recovery checkpoints and four continuations exactly. Backend readers verified all 209
  corpus/interruption/continuation records. All 1,345 retained files stayed byte-identical,
  including the original 1,247 and the 1,281 present after interruption. Evidence:
  /tmp/almg-corpus-resumed-reference-native-qa/verification.json, interrupt.log,
  recover.log, restart.log and raw native selected/review/recovered/continuation captures.
- Validation: 651 Python tests passed with Metal enabled and warnings as errors;
  90 Flutter tests passed and analysis was clean. New real-worker tests interrupt
  reference recovery for both optimizers, verify current approval/parent/state/counters,
  reject active owners and missing reapproval, preserve all source bytes and recover
  again to exact completed results. UI coverage labels resumed reference state, excludes
  recorded-training/completed-model actions and requires another reference approval.
- Remaining: durable transition into recorded training inside reference-recovery workers,
  arbitrary interruption/admission/publication points, physical OS/power-loss verification,
  broader model/sequence/batch/budget support, profiling and language-quality/50M–100M
  acceptance. This validates reference-phase process interruption, not general OS recovery.
  Independent hardware/user-action blockers stay open and skipped; P3-LMF-01 remains
  complete for its recorded architecture scope. No external collection occurred;
  generated artifacts, downloaded weights and unrelated user edits remain outside Git.

P3-LMF-06 partial progress · durable reference-to-training transition · 2026-11-21:
- [ ] P3-LMF-06 remains open. Reference-recovery workers now retain their completed
  reference when entering recorded training and publish training start/quarter/midpoint
  checkpoints. Version-13 immutable records bind the current reference-recovery approval
  and ancestry, completed reference weights/moments/log, active training weights/moments/
  scheduler and update prefix, tokenizer and originating worker ownership. Midpoint files
  are included after that point. Existing flushed, manifest-last publication applies;
  the existing eight-checkpoint admission reserve covers both phases.
- Validation distinguishes version-13 recorded-training state from version-12 reference
  state while preserving version-5 through version-12 reads. Per-origin discovery prefers
  training over reference, including training zero over reference thirty. Version-13 points
  offer recorded-training recovery only: a new resource review/confirmation reuses the
  completed reference and restores the saved training counter, carrying the reference
  ancestry into the existing sixteen-ancestor recorded-training limit. Reference recovery
  cannot be approved against a training-phase point.
- Native verification used rebuilt ALMG and offline fixture backend port 28925 with the
  704-parameter, sequence-eight, two-row/two-microbatch forty-update corpus. For both FP32
  SGD and mixed FP16 AdamW, approved recovery from retained reference twenty was interrupted
  after its own training-start zero snapshot; recovery from reference thirty was interrupted
  after its own training-twenty snapshot. Each child PID, command and parent backend was
  checked before SIGKILL. Discovery selected the advanced training phase/counter and hid
  earlier generations while retaining all fourteen new snapshots. No terminal original
  run or cancellation receipt was fabricated.
- After app/backend restart, all four required recorded-training resource review and
  explicit confirmation. Training-start sources executed forty remaining training updates;
  midpoint sources executed twenty; all executed zero reference updates and reused their
  completed reference. Results had recorded-training ancestry depth three, exact optimizer/
  scheduler restoration, zero final reference weight/moment error and matching reloaded
  CPU generation. Each also completed separately approved update-20 to update-40 midpoint
  continuation with zero reference weight difference. Completed recovery origins were
  excluded from interruption discovery while their published snapshots remained retained.
- A final app/backend restart reopened twenty ordinary records, four transition checkpoints
  and four continuations exactly. Readers verified all 243 corpus/interruption/continuation
  records. All 1,567 retained files stayed byte-identical, including the original 1,345 and
  the 1,431 present after interruption. Evidence:
  /tmp/almg-corpus-reference-training-native-qa/verification.json, interrupt.log,
  recover.log, recover-remaining.log, restart.log and raw native captures. One modal
  left a stale accessibility tree after a successful recovery/continuation; refreshing
  the temporary driver restored access and the remaining cases resumed without rerunning
  that completed case. The initial fixture selector reused
  an older carrier ID; the older record was preserved, a unique fixture ID was selected,
  and verification restarted before any training had begun. That diagnostic log is retained.
- Validation: 652 Python tests passed with Metal enabled and warnings as errors;
  91 Flutter tests passed and analysis was clean. The strengthened original-file guard
  also passed its targeted real-worker rerun. New actual-worker tests interrupt the
  phase transition for both optimizers, check ancestry/state/counters and liveness,
  reject reference-phase recovery and missing reapproval, and complete recorded-training
  recovery exactly without changing any retained file. UI coverage labels the transition,
  excludes reference/completed-model actions and requires recorded-training approval.
- Remaining: arbitrary interruption/admission/publication points, physical OS/power-loss
  verification, broader model/sequence/batch/budget support, profiling and language-quality/
  50M–100M acceptance. This verifies process recovery at published transition points,
  not general OS recovery. Independent hardware/user-action blockers remain open and
  skipped; P3-LMF-01 remains complete for its recorded architecture scope. No external
  collection occurred; generated artifacts, weights and unrelated edits are outside Git.

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
