import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import 'project_settings.dart';
import 'attachment_preview.dart';
import 'chat_export.dart';
import 'backend_address.dart';

/// Refreshes immediately, then retries while the local backend is unavailable.
Future<void> retryBackendConnection({
  required Future<void> Function() refresh,
  required bool Function() shouldRetry,
  Duration retryInterval = const Duration(milliseconds: 700),
  Duration retryWindow = const Duration(seconds: 20),
}) async {
  await refresh();
  final wait = Stopwatch()..start();
  while (shouldRetry() && wait.elapsed < retryWindow) {
    await Future<void>.delayed(retryInterval);
    if (!shouldRetry()) break;
    await refresh();
  }
}

/// Displays local conversations and links to model settings and training.
class ChatPage extends StatefulWidget {
  /// Creates the chat workspace with its training destination.
  const ChatPage({
    super.key,
    required this.trainingPage,
    this.modelLibraryPage,
    this.initialProject,
    this.initialChat,
  });

  /// Screen opened by the training action.
  final Widget trainingPage;
  final Widget? modelLibraryPage;
  final String? initialProject;
  final String? initialChat;

  /// Creates the state that owns the chat session.
  @override
  State<ChatPage> createState() => _ChatPageState();
}

/// Coordinates chat navigation, streaming replies, and local model controls.
class _ChatPageState extends State<ChatPage> {
  final _client = HttpClient()..connectionTimeout = const Duration(seconds: 4);
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _composerFocus = FocusNode();
  bool _followReply = true;
  bool _scrollScheduled = false;
  final _messages = <Map<String, String>>[];
  Map<String, dynamic>? _model;
  List<dynamic> _chats = [];
  List<dynamic> _projects = [];
  String? _projectId;
  bool _sidebarOpen = true;
  bool _projectsOpen = true;
  bool _conversationsOpen = true;
  String? _chatId;
  bool _openingChat = false;
  Timer? _poll;
  String? _error;
  bool _sending = false;
  bool _deleting = false;
  bool _stopping = false;
  String? _streamId;
  String? _replyStatus;
  String? _interruptedReply;
  String _search = '';
  Timer? _searchTimer;
  bool _recall = true;
  bool _checking = false;
  bool _backendOffline = false;
  final _downloadClock = Stopwatch()..start();
  int? _downloadSampleMs;
  double? _downloadBytesPerSecond;
  bool _runtimeStopped = false;
  bool _stoppingRuntime = false;
  bool _restartingBackend = false;
  String? _restartError;
  bool _showSettings = false;

  final _drafts = <String, String>{};
  final _pendingReplies = <String, Map<String, String>>{};
  String? _retryToken;
  String? _retryPayload;
  Future<void> _draftWrites = Future<void>.value();
  bool _draftsLoaded = false;

  File get _chatPreferences => File(
    '${Platform.environment['APPDATA'] ?? Platform.environment['HOME'] ?? Directory.systemTemp.path}'
    '${Platform.isMacOS ? '/Library/Application Support' : ''}/ALMG/${const String.fromEnvironment('ALMG_CHAT_STATE_NAME', defaultValue: 'chat-preferences.json')}',
  );

  String get _draftKey => _chatId ?? 'new:${_projectId ?? 'personal'}';

  Future<void> _loadChatPreferences() async {
    try {
      final saved = jsonDecode(await _chatPreferences.readAsString()) as Map;
      if (!mounted) return;
      final drafts = saved['drafts'];
      if (drafts is Map<String, dynamic>) {
        for (final entry in drafts.entries) {
          if (entry.value case final String draft) _drafts[entry.key] = draft;
        }
      }
      if (saved['pending_replies'] case final Map pending) {
        for (final entry in pending.entries) {
          if (entry.key is String && entry.value is Map) {
            final value = entry.value as Map;
            if (value['token'] is String && RegExp(r'^[a-f0-9]{32}$').hasMatch(value['token'] as String) && value['payload'] is String) {
              _pendingReplies[entry.key as String] = {
                'token': value['token'] as String, 'payload': value['payload'] as String,
                if (value['partial'] is String) 'partial': value['partial'] as String,
              };
            }
          }
        }
      }
      setState(() => _recall = saved['recall'] != false);
      if (_input.text.isEmpty) _input.text = _drafts[_draftKey] ?? '';
      _restorePendingReply();
    } on FileSystemException {
      // The first session has no saved preferences.
    } on TypeError {
      // Ignore preferences written in an unsupported format.
    } on FormatException {
      // An interrupted or invalid preferences file can be replaced.
    } finally {
      if (mounted) {
        _draftsLoaded = true;
        _rememberDraft();
      }
    }
  }

  void _setRecall(bool value) {
    setState(() => _recall = value);
    _saveChatPreferences();
  }

  void _rememberDraft() {
    if (!_draftsLoaded || _sending) return;
    if (_input.text == (_drafts[_draftKey] ?? '')) return;
    if (_input.text.isEmpty) {
      _drafts.remove(_draftKey);
    } else {
      _drafts[_draftKey] = _input.text;
    }
    _saveChatPreferences();
  }

  void _restorePendingReply() {
    final pending = _pendingReplies[_draftKey];
    _interruptedReply = pending?['partial'];
    if (pending == null) return;
    try {
      final payload = jsonDecode(pending['payload']!) as Map;
      if (payload['text'] == _input.text.trim() && payload['attachment'] is Map) {
        _attachment = Map<String, String>.from(payload['attachment'] as Map);
      }
    } on FormatException { /* Ignore invalid recovery metadata. */ }
      on TypeError { /* Ignore unsupported recovery metadata. */ }
  }

  Future<void> _saveChatPreferences({bool failOnError = false}) {
    final snapshot = jsonEncode({'recall': _recall, 'drafts': _drafts, 'pending_replies': _pendingReplies});
    final write = _draftWrites.then((_) async {
      final file = _chatPreferences;
      try {
        await file.parent.create(recursive: true);
        final temporary = File('${file.path}.tmp');
        await temporary.writeAsString(snapshot);
        await temporary.rename(file.path);
      } on FileSystemException catch (error) {
        if (mounted) {
          setState(() => _error = 'Could not save chat preferences. $error');
        }
        rethrow;
      }
    });
    _draftWrites = write.catchError((Object _) {});
    return failOnError ? write : _draftWrites;
  }

  /// Registers keyboard shortcuts and loads the initial backend state.
  @override
  void initState() {
    super.initState();
    _input.addListener(_rememberDraft);
    unawaited(_loadChatPreferences());
    FocusManager.instance.addEarlyKeyEventHandler(_sendShortcut);
    _projectId = widget.initialProject;
    _refresh();
    if (widget.initialChat case final String id) unawaited(_openChat(id));
    _loadHistory();
    _loadProjects();
  }

  /// Handles the platform-specific send shortcut while the composer has focus.
  KeyEventResult _sendShortcut(KeyEvent event) {
    final keyboard = HardwareKeyboard.instance;
    final modifier = Platform.isMacOS
        ? keyboard.isMetaPressed
        : keyboard.isControlPressed;
    if (!_composerFocus.hasFocus ||
        event is! KeyDownEvent ||
        event.logicalKey != LogicalKeyboardKey.enter ||
        !modifier ||
        keyboard.isShiftPressed ||
        keyboard.isAltPressed) {
      return KeyEventResult.ignored;
    }
    _send();
    return KeyEventResult.handled;
  }

  /// Tracks whether streaming updates should follow the bottom of the transcript.
  bool _onChatScroll(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    if (notification is ScrollUpdateNotification) {
      final delta = notification.scrollDelta ?? 0;
      if (delta < 0) {
        _followReply = false;
      } else if (delta > 0 && notification.metrics.extentAfter < 4) {
        _followReply = true;
      }
    }
    return false;
  }

  /// Opens a local desktop API request and returns its response stream.
  Future<HttpClientResponse> _openRequest(String path, {Object? body}) async {
    final request = await _client.openUrl(
      body == null ? 'GET' : 'POST',
      Uri.parse('http://127.0.0.1:$backendPort$path'),
    );
    request.headers.set('X-Model-Studio', 'desktop');
    if (body != null) {
      final bytes = utf8.encode(jsonEncode(body));
      request.headers.contentType = ContentType.json;
      request.contentLength = bytes.length;
      request.add(bytes);
    }
    return request.close().timeout(
      path == '/model'
          ? const Duration(seconds: 5)
          : const Duration(minutes: 10),
    );
  }

  /// Decodes a local API response and reports backend errors.
  Future<Map<String, dynamic>> _request(String path, {Object? body}) async {
    final response = await _openRequest(path, body: body);
    final result = jsonDecode(
      await response.transform(utf8.decoder).join(),
    ) as Map<String, dynamic>;
    if (response.statusCode >= 400) {
      throw FormatException(result['error'].toString());
    }
    return result;
  }

  /// Refreshes model status and schedules polling while the runtime is available.
  Future<void> _refresh({String? action, bool background = false}) async {
    if (_checking || _stoppingRuntime || _runtimeStopped) return;
    _poll?.cancel();
    setState(() {
      _checking = true;
      if (!background) _error = null;
    });
    try {
      final model = action == null
          ? await _request('/model')
          : await _request('/model/setup', body: {'action': action});
      if (!mounted) return;
      final reconnecting = _backendOffline;
      setState(() {
        final now = _downloadClock.elapsedMilliseconds;
        final previousMs = _downloadSampleMs;
        final previousBytes = _model?['downloaded_bytes'] as num?;
        final currentBytes = model['downloaded_bytes'] as num?;
        final transferring = model['phase'] == 'downloading';
        _downloadBytesPerSecond =
            transferring &&
                !reconnecting &&
                previousMs != null &&
                now > previousMs &&
                previousBytes != null &&
                currentBytes != null &&
                currentBytes >= previousBytes
            ? (currentBytes - previousBytes) * 1000 / (now - previousMs)
            : null;
        _downloadSampleMs = transferring ? now : null;
        _model = model;
        _backendOffline = false;
        if (reconnecting) _error = null;
      });
      if (reconnecting) {
        unawaited(Future.wait([_loadProjects(), _loadHistory()]));
      }
      _poll = Timer(
        Duration(seconds: model['downloading'] == true ? 3 : 10),
        () => _refresh(background: true),
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          if (error is SocketException || error is TimeoutException) {
            _backendOffline = true;
            _poll = Timer(
              const Duration(seconds: 5),
              () => _refresh(background: true),
            );
          } else if (!background) {
            _error = error.toString();
          }
        });
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  /// Stops the local runtime and suspends automatic reconnection.
  Future<void> _stopRuntime() async {
    if (_checking || _stoppingRuntime || _sending) return;
    _poll?.cancel();
    setState(() {
      _stoppingRuntime = true;
      _error = null;
    });
    try {
      await _request('/backend/stop', body: <String, dynamic>{});
      if (!mounted) return;
      setState(() {
        _runtimeStopped = true;
        _backendOffline = true;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
      _poll = Timer(
        const Duration(seconds: 5),
        () => _refresh(background: true),
      );
    } finally {
      if (mounted) setState(() => _stoppingRuntime = false);
    }
  }

  /// Retries the local connection to activate and reconnect to the backend.
  Future<void> _restartBackend() async {
    if (_restartingBackend) return;
    setState(() {
      _restartingBackend = true;
      _runtimeStopped = false;
      _restartError = null;
    });
    try {
      if (!Platform.isMacOS) {
        throw UnsupportedError(
          'Start the Python backend from the project folder.',
        );
      }
      // The launch agent starts Python when this connection reaches its socket.
      await retryBackendConnection(
        refresh: () => _refresh(background: true),
        shouldRetry: () => mounted && _backendOffline,
      );
      if (mounted && _backendOffline) {
        setState(
          () => _restartError = 'The backend did not respond. Check that the ALMG backend service is registered.',
        );
      }
    } on Exception catch (error) {
      if (mounted) setState(() => _restartError = error.toString());
    } finally {
      if (mounted) setState(() => _restartingBackend = false);
    }
  }

  /// Shows the current offline state and offers a restart action.
  Widget _backendRecovery() => Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      Text(
        _runtimeStopped
            ? 'Runtime stopped.'
            : 'The local backend is unavailable.',
      ),
      if (_restartError case final String error) SelectableText(error),
      if (Platform.isMacOS) ...[
        const SizedBox(height: 8),
        IconButton.filled(
          tooltip: _restartingBackend ? 'Starting backend…' : 'Restart backend',
          onPressed: _restartingBackend ? null : _restartBackend,
          icon: _restartingBackend
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.restart_alt),
        ),
      ] else
        const Text(
          'Start the Python backend, then select Check setup in Settings.',
        ),
    ],
  );

  /// Loads the conversation list for the selected project.
  Future<void> _loadHistory() async {
    try {
      final projectId = _projectId;
      final query = _search;
      final result = await _request(
        Uri(
          path: '/chats',
          queryParameters: {
            'project_id': ?projectId,
            if (query.isNotEmpty) 'q': query,
          },
        ).toString(),
      );
      if (mounted && _projectId == projectId && _search == query) {
        setState(() => _chats = result['chats'] as List);
      }
    } catch (error) {
      if (mounted && _model != null) {
        setState(() => _error = 'Could not load local chat history. $error');
      }
    }
  }

  /// Loads the sidebar project list from the backend.
  Future<void> _loadProjects() async {
    try {
      final result = await _request('/projects');
      if (mounted) setState(() => _projects = result['projects'] as List);
    } catch (error) {
      if (mounted && _model != null) {
        setState(() => _error = 'Could not load projects. $error');
      }
    }
  }

  /// Switches the sidebar and conversation state to another project.
  void _selectProject(String? id) {
    if (_sending || _openingChat || _projectId == id) return;
    setState(() {
      _projectId = id;
      _search = '';
      _chats = [];
    });
    _newChat();
    _loadHistory();
  }

  /// Prompts for a project name and opens the resulting project.
  Future<void> _createProject() async {
    var draft = '';
    final name = await showDialog<String>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('New project'),
        content: TextField(
          autofocus: true,
          maxLength: 80,
          decoration: const InputDecoration(labelText: 'Project name'),
          onChanged: (value) => draft = value,
          onSubmitted: (value) => Navigator.pop(dialog, value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialog, draft),
            child: const Text('Create'),
          ),
        ],
      ),
    );
    if (!mounted || name == null || name.trim().isEmpty) return;
    try {
      final project = await _request('/projects', body: {'name': name.trim()});
      if (!mounted) return;
      setState(() => _projects = [..._projects, project]);
      _selectProject(project['id'] as String);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Loads and opens the selected project’s settings.
  Future<void> _projectSettings() async {
    final id = _projectId;
    if (id == null) return;
    try {
      final project = await _request('/projects/$id');
      if (!mounted || _projectId != id) return;
      await showDialog<bool>(
        context: context,
        builder: (_) => ProjectSettings(project: project, request: _request),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Lets the user choose a destination for an existing conversation.
  Future<void> _moveChat(String id) async {
    final destinations = <String, String>{
      if (_projectId != null) '': 'Personal chats',
      for (final project in _projects)
        if (project['id'] != _projectId)
          project['id'] as String: project['name'] as String,
    };
    final target = await showDialog<String>(
      context: context,
      builder: (dialog) {
        String? selected;
        return StatefulBuilder(
          builder: (context, refresh) => AlertDialog(
            icon: const Icon(Icons.drive_file_move_outlined),
            title: const Text('Move conversation'),
            scrollable: true,
            content: SizedBox(
              width: 360,
              child: RadioGroup<String>(
                groupValue: selected,
                onChanged: (value) => refresh(() => selected = value),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final destination in destinations.entries)
                      RadioListTile<String>(
                        value: destination.key,
                        title: Text(destination.value),
                        secondary: Icon(
                          destination.key.isEmpty
                              ? Icons.chat_bubble_outline
                              : Icons.folder_outlined,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialog),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: selected == null
                    ? null
                    : () => Navigator.pop(dialog, selected),
                child: const Text('Move'),
              ),
            ],
          ),
        );
      },
    );
    if (!mounted || target == null) return;
    try {
      await _request(
        '/chats/move',
        body: {'id': id, 'project_id': target.isEmpty ? null : target},
      );
      if (!mounted) return;
      if (_chatId == id) _newChat();
      await _loadHistory();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Loads an existing transcript and scrolls to its most recent turn.
  Future<void> _openChat(String id) async {
    setState(() {
      _openingChat = true;
      _replyStatus = null;
      _interruptedReply = null;
      _error = null;
    });
    try {
      final result = await _request('/chats/$id');
      if (!mounted) return;
      final messages = (result['messages'] as List).map(
        (message) => Map<String, String>.from(message as Map),
      );
      setState(() {
        _chatId = id;
        _attachment = null;
        _input.text = _drafts[_draftKey] ?? '';
        _restorePendingReply();
        _messages
          ..clear()
          ..addAll(messages);
      });
      _followReply = true;
      _scrollToEnd();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _openingChat = false);
    }
  }

  /// Clears the active transcript and composer for a new conversation.
  void _newChat() {
    setState(() {
      _chatId = null;
      _attachment = null;
      _replyStatus = null;
      _messages.clear();
      _interruptedReply = null;
      _input.text = _drafts[_draftKey] ?? '';
      _restorePendingReply();
      _error = null;
    });
  }

  /// Creates a branch and optionally fills or sends a replacement prompt.
  Future<void> _branchFrom(
    int messageCount, {
    String? prompt,
    bool send = false,
  }) async {
    final source = _chatId;
    if (source == null || _openingChat || _sending || _deleting) return;
    final draft = _input.text;
    late final String branchNotice;
    setState(() {
      _openingChat = true;
      _error = null;
    });
    try {
      final branch = await _request(
        '/chats/branch',
        body: {'id': source, 'message_count': messageCount},
      );
      if (!mounted) return;
      branchNotice = 'Created branch in ${branch['project_name'] ?? 'the same project'}. '
          'Original conversation preserved: ${branch['source_title'] ?? 'source chat'}.';
      setState(() {
        if (branch.containsKey('project_id')) _projectId = branch['project_id'] as String?;
        _chatId = branch['id'] as String;
        if (prompt != null) _attachment = null;
        _messages.removeRange(messageCount, _messages.length);
        _replyStatus = null;
        _interruptedReply = null;
        _input.text = prompt ?? draft;
      });
      unawaited(_loadHistory());
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
      return;
    } finally {
      if (mounted) setState(() => _openingChat = false);
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(branchNotice)));
    if (send) {
      await _send();
    } else {
      _composerFocus.requestFocus();
      _scrollToEnd();
    }
  }

  Map<String, String>? _attachment;

  /// Reads one file into the composer while enforcing the attachment limit.
  Future<void> _attachFile() async {
    final chat = _chatId;
    final project = _projectId;
    try {
      final file = await openFile();
      if (file == null || !mounted) return;
      if (await file.length() > 1000000) {
        throw const FormatException('Choose a file up to 1 MB.');
      }
      final bytes = await file.readAsBytes();
      if (bytes.length > 1000000) {
        throw const FormatException('Choose a file up to 1 MB.');
      }
      if (!mounted || chat != _chatId || project != _projectId || _sending) {
        return;
      }
      final extension = file.name.split('.').last.toLowerCase();
      String? extracted;
      if (Platform.isMacOS && visualAttachmentExtensions.contains(extension)) {
        const channel = MethodChannel('almg/attachments');
        extracted = await channel.invokeMethod<String>('extract', {
          'format': extension,
          'bytes': bytes,
        });
      } else {
        extracted = visualAttachmentExtensions.contains(extension) ? '' : readableAttachmentText(bytes);
      }
      extracted = boundedAttachmentText(extracted ?? '');
      if (!mounted || chat != _chatId || project != _projectId || _sending) {
        return;
      }
      setState(() {
        _attachment = {
          'name': file.name,
          'data': base64Encode(bytes),
          'extracted': ?extracted,
        };
        _error = null;
      });
      _composerFocus.requestFocus();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Streams a reply and restores the draft if generation is interrupted.
  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || !_draftsLoaded || _sending || _openingChat || _deleting) return;
    final attachment = _attachment;
    final draftKey = _draftKey;
    final payload = {
      'id': _chatId,
      'text': text,
      'project_id': _projectId,
      'attachment': ?attachment,
      'recall': _recall,
    };
    final fingerprint = jsonEncode(payload);
    final pending = _pendingReplies[draftKey];
    if (pending?['payload'] == fingerprint) {
      _retryPayload = fingerprint;
      _retryToken = pending!['token'];
    }
    if (_retryPayload != fingerprint) {
      final random = Random.secure();
      _retryPayload = fingerprint;
      _retryToken = List.generate(
        32,
        (_) => random.nextInt(16).toRadixString(16),
      ).join();
    }

    _pendingReplies[draftKey] = {'token': _retryToken!, 'payload': fingerprint,
      if (pending?['partial'] case final String partial) 'partial': partial};
    _drafts[draftKey] = text;
    final answer = {'role': 'assistant', 'content': ''};
    setState(() {
      _sending = true;
      _interruptedReply = null;
      _error = null;
      _replyStatus = null;
      _messages.addAll([
        {
          'role': 'user',
          'content': text,
          if (attachment != null) 'file_name': attachment['name']!,
        },
        answer,
      ]);
      _input.clear();
    });
    _followReply = true;
    _scrollToEnd();
    try {
      await _saveChatPreferences(failOnError: true);
      if (!mounted) return;
      final response = await _openRequest(
        '/chats/stream',
        body: {...payload, 'token': _retryToken},
      );
      if (response.statusCode != 200) {
        await response.drain<void>();
        throw const FormatException(
          'Could not start a reply. Check that the updated backend is running.',
        );
      }
      Map<String, dynamic>? finished;
      final lines = response
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .timeout(const Duration(minutes: 10));
      await for (final line in lines) {
        if (!mounted) return;
        final event = jsonDecode(line) as Map<String, dynamic>;
        if (event['error'] case final String error) {
          throw FormatException(error);
        }
        if (event['request_id'] case final String id) {
          setState(() => _streamId = id);
        }
        if (event['delta'] case final String delta) {
          setState(() => answer['content'] = answer['content']! + delta);
          _scrollToEnd();
        }
        if (event['done'] case final Map<String, dynamic> result) {
          finished = result;
          break;
        }
      }
      if (!mounted) return;
      if (finished == null) {
        throw const FormatException('The reply was interrupted. Try again.');
      }
      final result = finished;
      setState(() {
        final id = result['id'] as String?;
        if (id == null) {
          _messages.removeRange(_messages.length - 2, _messages.length);
          _input.text = text;
        } else {
          _retryPayload = null;
          _retryToken = null;
          _drafts.remove(draftKey);
          _pendingReplies.remove(draftKey);
          _saveChatPreferences();
          _chatId = id;
          _attachment = null;
          answer['content'] = result['reply'] as String;
        }
        _replyStatus = switch (result['finish_reason']) {
          'length' => 'Response limit reached. Ask Qwen to continue.',
          'cancelled' => 'Generation stopped.',
          _ => null,
        };
      });
      _loadHistory();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _messages.removeRange(_messages.length - 2, _messages.length);
        _input.text = text;
        final partial = answer['content']!;
        _interruptedReply = partial.isEmpty ? null : partial;
        if (partial.isNotEmpty) _pendingReplies[draftKey]!['partial'] = partial;
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _sending = false;
          _stopping = false;
          _streamId = null;
        });
        _saveChatPreferences();
      }
    }
  }

  /// Requests cancellation of the active reply stream.
  Future<void> _stop() async {
    final id = _streamId;
    if (id == null || _stopping) return;
    setState(() => _stopping = true);
    try {
      await _request('/chats/stop', body: {'request_id': id});
    } catch (error) {
      if (mounted && _streamId == id) {
        setState(() {
          _stopping = false;
          _error = error.toString();
        });
      }
    }
  }

  /// Prompts for a replacement title and updates the project or conversation.
  Future<void> _rename(String id, String title, {bool project = false}) async {
    var draft = title;
    final name = await showDialog<String>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(project ? 'Rename project' : 'Rename conversation'),
        content: TextFormField(
          initialValue: title,
          autofocus: true,
          maxLength: 80,
          onChanged: (value) => draft = value,
          onFieldSubmitted: (value) => Navigator.pop(dialog, value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialog, draft),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (!mounted || name == null || name.trim().isEmpty) return;
    try {
      await _request(
        project ? '/projects/rename' : '/chats/rename',
        body: {'id': id, (project ? 'name' : 'title'): name.trim()},
      );
      if (project) {
        await _loadProjects();
      } else {
        await _loadHistory();
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Confirms and removes a project or conversation through the local API.
  Future<void> _delete(String id, String name, {bool project = false}) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(project ? 'Delete project?' : 'Delete conversation?'),
        content: Text(
          project
              ? 'Delete “$name” and its instructions and reference files? Its conversations will move to Personal chats.'
              : 'Delete “$name” and all its messages? This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(dialog).colorScheme.error,
              foregroundColor: Theme.of(dialog).colorScheme.onError,
            ),
            onPressed: () => Navigator.pop(dialog, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true) return;
    setState(() => _deleting = true);
    try {
      await _request(
        project ? '/projects/delete' : '/chats/delete',
        body: {'id': id},
      );
      if (!mounted) return;
      if (project) {
        if (_projectId == id) _selectProject(null);
        await _loadProjects();
        await _loadHistory();
      } else {
        if (_chatId == id) _newChat();
        await _loadHistory();
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _deleting = false);
    }
  }

  /// Formats a byte count in decimal MB or GB.
  String _size(num bytes) => bytes >= 1000000000
      ? '${(bytes / 1000000000).toStringAsFixed(2)} GB'
      : '${(bytes / 1000000).toStringAsFixed(1)} MB';

  /// Schedules a scroll after layout when following the latest reply.
  void _scrollToEnd() {
    if (!_followReply || _scrollScheduled) return;
    _scrollScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollScheduled = false;
      if (mounted && _followReply && _scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  /// Releases the chat controllers, timers, and network client.
  @override
  void dispose() {
    _searchTimer?.cancel();
    _poll?.cancel();
    _client.close(force: true);
    FocusManager.instance.removeEarlyKeyEventHandler(_sendShortcut);
    _composerFocus.dispose();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  /// Builds the chat workspace or its setup and recovery screens.
  @override
  Widget build(BuildContext context) {
    final model = _model;
    final ready =
        model?['ready'] == true &&
        model?['runtime'] == true &&
        model?['supported'] == true &&
        model?['downloading'] == false;
    final colors = Theme.of(context).colorScheme;
    if (_showSettings) return _buildSettings(ready);
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'ALMG',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        titleSpacing: 20,
        scrolledUnderElevation: 0,
        backgroundColor: colors.surface,
        shape: Border(bottom: BorderSide(color: colors.outlineVariant)),
        actions: [
          if (widget.modelLibraryPage case final Widget library)
            IconButton(
              tooltip: 'Model Library',
              onPressed: () =>
                  Navigator.of(context)
                      .push(MaterialPageRoute<void>(builder: (_) => library)),
              icon: const Icon(Icons.inventory_2_outlined),
            ),
          IconButton(
            tooltip: 'Training',
            onPressed: _model != null && !_backendOffline
                ? () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => widget.trainingPage,
                    ),
                  )
                : null,
            icon: const Icon(Icons.model_training_outlined),
          ),
          IconButton(
            tooltip: 'Settings',
            onPressed: () => setState(() => _showSettings = true),
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
      body: _runtimeStopped || (_backendOffline && !ready)
          ? Center(child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: SizedBox(width: 600, child: Column(mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  _backendRecovery(),
                  if (_input.text.isNotEmpty) ...[
                    const SizedBox(height: 24),
                    const Text('Saved unsent draft', style: TextStyle(fontWeight: FontWeight.bold)),
                    SelectableText(_input.text),
                  ],
                  if (_interruptedReply case final String partial) ...[
                    const SizedBox(height: 24),
                    const Text('Interrupted reply', style: TextStyle(fontWeight: FontWeight.bold)),
                    SelectableText(partial),
                  ],
                ])),
            ))
          : ready
          ? LayoutBuilder(
              builder: (context, constraints) {
                final wide = constraints.maxWidth >= 700;
                return Row(
                  children: [
                    if (wide && _sidebarOpen) ...[
                      SizedBox(width: 260, child: _history()),
                      const VerticalDivider(width: 1),
                    ],
                    Expanded(child: _conversation(colors, wide: wide)),
                  ],
                );
              },
            )
          : Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'Local model setup is required',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Set up and verify Qwen3.8-27B in Settings to use ALMG.',
                  ),
                  const SizedBox(height: 16),
                  IconButton.filled(
                    tooltip: 'Open Settings',
                    onPressed: () => setState(() => _showSettings = true),
                    icon: const Icon(Icons.settings_outlined),
                  ),
                ],
              ),
            ),
    );
  }

  Future<void> _exportMarkdown(String id, String title, {bool saveFile = false}) async {
    try {
      final result = await _request('/chats/$id');
      if (!mounted) return;
      final document = conversationMarkdown(title, result['messages'] as List);
      if (saveFile) {
        final destination = await getSaveLocation(suggestedName: 'almg-conversation.md',
          acceptedTypeGroups: const [XTypeGroup(label: 'Markdown', extensions: ['md'])]);
        if (destination == null) return;
        await XFile.fromData(Uint8List.fromList(utf8.encode(document)), mimeType: 'text/markdown',
          name: 'almg-conversation.md').saveTo(destination.path);
      } else {
        await Clipboard.setData(ClipboardData(text: document));
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(saveFile ? 'Conversation saved as Markdown' : 'Conversation copied as Markdown')),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Builds the project list, conversation controls, and search field.
  Widget _history({bool modal = false}) {
    final colors = Theme.of(context).colorScheme;
    final busy = _sending || _openingChat || _deleting;
    return StatefulBuilder(
      builder: (context, refreshHistory) {
        return ColoredBox(
          color: colors.surfaceContainerLow,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: ListView(
              children: [
                Row(
                  children: [
                    IconButton(
                      tooltip: _projectsOpen
                          ? 'Collapse projects'
                          : 'Expand projects',
                      onPressed: () =>
                          refreshHistory(() => _projectsOpen = !_projectsOpen),
                      icon: Icon(
                        _projectsOpen ? Icons.expand_more : Icons.chevron_right,
                      ),
                    ),
                    const Expanded(child: Text('Projects')),
                    IconButton(
                      tooltip: 'New project',
                      icon: const Icon(
                        Icons.create_new_folder_outlined,
                        size: 20,
                      ),
                      onPressed: busy
                          ? null
                          : () {
                              if (modal) Navigator.pop(context);
                              _createProject();
                            },
                    ),
                  ],
                ),
                if (_projectsOpen)
                  for (final project in [
                    {'id': null, 'name': 'Personal chats'},
                    ..._projects,
                  ])
                    ListTile(
                      dense: true,
                      selected: project['id'] == _projectId,
                      selectedTileColor: colors.secondaryContainer,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                      leading: Icon(
                        project['id'] == null
                            ? Icons.chat_bubble_outline
                            : Icons.folder_outlined,
                        size: 18,
                      ),
                      title: Text(
                        project['name'] as String,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: project['id'] == null
                          ? null
                          : PopupMenuButton<String>(
                              tooltip: 'Project options',
                              enabled: !busy,
                              onSelected: (action) {
                                if (modal) Navigator.pop(context);
                                final id = project['id'] as String;
                                final name = project['name'] as String;
                                if (action == 'rename') {
                                  _rename(id, name, project: true);
                                } else {
                                  _delete(id, name, project: true);
                                }
                              },
                              itemBuilder: (_) => const [
                                PopupMenuItem(
                                  value: 'rename',
                                  child: Text('Rename project'),
                                ),
                                PopupMenuItem(
                                  value: 'delete',
                                  child: Text('Delete project'),
                                ),
                              ],
                            ),
                      onTap: busy
                          ? null
                          : () {
                              if (modal) Navigator.pop(context);
                              _selectProject(project['id'] as String?);
                            },
                    ),
                const SizedBox(height: 8),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Row(
                    children: [
                      IconButton.filledTonal(
                        tooltip: 'New chat',
                        onPressed: busy
                            ? null
                            : () {
                                if (modal) Navigator.pop(context);
                                _newChat();
                              },
                        icon: const Icon(Icons.edit_square),
                      ),
                      if (_projectId != null)
                        IconButton(
                          tooltip: 'Project settings',
                          onPressed: busy
                              ? null
                              : () {
                                  if (modal) Navigator.pop(context);
                                  _projectSettings();
                                },
                          icon: const Icon(Icons.tune),
                        ),
                    ],
                  ),
                ),
                Row(
                  children: [
                    IconButton(
                      tooltip: _conversationsOpen
                          ? 'Collapse conversations'
                          : 'Expand conversations',
                      onPressed: () => refreshHistory(
                        () => _conversationsOpen = !_conversationsOpen,
                      ),
                      icon: Icon(
                        _conversationsOpen
                            ? Icons.expand_more
                            : Icons.chevron_right,
                      ),
                    ),
                    const Expanded(child: Text('Conversations')),
                  ],
                ),
                if (_conversationsOpen) ...[
                  TextFormField(
                    key: ValueKey(_projectId),
                    initialValue: _search,
                    decoration: const InputDecoration(
                      hintText: 'Search conversations',
                      filled: true,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.all(Radius.circular(10)),
                        borderSide: BorderSide.none,
                      ),
                      prefixIcon: Icon(Icons.search),
                      isDense: true,
                    ),
                    onChanged: (value) {
                      setState(() => _search = value);
                      _searchTimer?.cancel();
                      _searchTimer = Timer(
                        const Duration(milliseconds: 250),
                        _loadHistory,
                      );
                    },
                  ),
                  const SizedBox(height: 8),
                  ListView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _chats.length,
                    itemBuilder: (context, index) {
                      final chat = _chats[index] as Map;
                      final id = chat['id'] as String;
                      return ListTile(
                        dense: true,
                        contentPadding: const EdgeInsets.only(
                          left: 10,
                          right: 4,
                        ),
                        horizontalTitleGap: 8,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                        selected: id == _chatId,
                        selectedTileColor: colors.secondaryContainer,
                        leading: const Icon(
                          Icons.chat_bubble_outline,
                          size: 18,
                        ),
                        title: Text(
                          chat['title'] as String,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: PopupMenuButton<String>(
                          tooltip: 'Conversation options',
                          enabled: !busy,
                          onSelected: (action) {
                            if (modal) Navigator.pop(context);
                            if (action == 'export' || action == 'save-markdown') {
                              _exportMarkdown(id, chat['title'] as String, saveFile: action == 'save-markdown');
                            } else if (action == 'move') {
                              _moveChat(id);
                            } else if (action == 'delete') {
                              _delete(id, chat['title'] as String);
                            } else {
                              _rename(id, chat['title'] as String);
                            }
                          },
                          itemBuilder: (_) => [
                            const PopupMenuItem(
                              value: 'export',
                              child: Text('Copy as Markdown'),
                            ),
                            const PopupMenuItem(
                              value: 'save-markdown',
                              child: Text('Save as Markdown'),
                            ),
                            const PopupMenuItem(
                              value: 'rename',
                              child: Text('Rename'),
                            ),
                            const PopupMenuItem(
                              value: 'delete',
                              child: Text('Delete conversation'),
                            ),
                            if (_projects.isNotEmpty)
                              const PopupMenuItem(
                                value: 'move',
                                child: Text('Move conversation'),
                              ),
                          ],
                        ),
                        onTap: busy
                            ? null
                            : () {
                                if (modal) Navigator.pop(context);
                                _openChat(id);
                              },
                      );
                    },
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  /// Builds the transcript with message actions and the composer.
  Widget _conversation(ColorScheme colors, {required bool wide}) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 820),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  IconButton(
                    tooltip: wide && _sidebarOpen
                        ? 'Hide sidebar'
                        : 'Show sidebar',
                    icon: const Icon(Icons.view_sidebar_outlined),
                    onPressed: () {
                      if (wide) {
                        setState(() => _sidebarOpen = !_sidebarOpen);
                      } else {
                        showModalBottomSheet<void>(
                          context: context,
                          builder: (_) => _history(modal: true),
                        );
                      }
                    },
                  ),
                  Container(
                    padding: const EdgeInsets.all(7),
                    decoration: BoxDecoration(
                      color: colors.secondaryContainer,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(
                      Icons.smart_toy_outlined,
                      size: 18,
                      color: colors.onSecondaryContainer,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'Qwen3.8-27B',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ],
              ),
              SwitchListTile.adaptive(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('Use other conversations'),
                subtitle: const Text('Use related messages from other chats in this project.'),
                value: _recall,
                onChanged: _sending || _openingChat ? null : _setRecall,
              ),
              const SizedBox(height: 12),
              if (_backendOffline) _backendRecovery(),
              if (_sending || _openingChat) const LinearProgressIndicator(),
              if (_error case final String error)
                Text(error, style: TextStyle(color: colors.error)),
              Expanded(
                child: _messages.isEmpty
                    ? Center(
                        child: Text(
                          'What would you like to explore?',
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                      )
                    : NotificationListener<ScrollNotification>(
                        onNotification: _onChatScroll,
                        child: ListView.builder(
                          controller: _scroll,
                          itemCount: _messages.length,
                          itemBuilder: (context, index) {
                            final message = _messages[index];
                            final user = message['role'] == 'user';
                            return Align(
                              alignment: user
                                  ? Alignment.centerRight
                                  : Alignment.centerLeft,
                              child: Container(
                                constraints: BoxConstraints(
                                  maxWidth: user ? 560 : 720,
                                ),
                                margin: const EdgeInsets.symmetric(vertical: 8),
                                padding: const EdgeInsets.all(16),
                                decoration: BoxDecoration(
                                  color: user
                                      ? colors.primaryContainer
                                      : colors.surfaceContainerLow,
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      user ? 'You' : 'Qwen',
                                      style: Theme.of(context)
                                          .textTheme
                                          .labelMedium,
                                    ),
                                    const SizedBox(height: 6),
                                    if (message['file_name']
                                        case final String name
                                        when name.isNotEmpty)
                                      Text(
                                        name,
                                        style: Theme.of(context)
                                            .textTheme
                                            .labelMedium,
                                      ),
                                    if (user)
                                      SelectableText(message['content']!)
                                    else
                                      _replyMarkdown(
                                        message['content']!.isEmpty
                                            ? 'Thinking…'
                                            : message['content']!,
                                      ),
                                    if (_chatId != null &&
                                        !_sending &&
                                        !_openingChat &&
                                        !_deleting)
                                      Wrap(
                                        children: [
                                          IconButton(
                                            tooltip: 'Branch from this message',
                                            icon: const Icon(
                                              Icons.call_split,
                                              size: 17,
                                            ),
                                            onPressed: () =>
                                                _branchFrom(index + 1),
                                          ),
                                          if (user)
                                            IconButton(
                                              tooltip: 'Edit in a new chat',
                                              icon: const Icon(
                                                Icons.edit_outlined,
                                                size: 17,
                                              ),
                                              onPressed: () => _branchFrom(
                                                index,
                                                prompt: message['content'],
                                              ),
                                            ),
                                          if (!user &&
                                              index > 0 &&
                                              _messages[index - 1]['role'] ==
                                                  'user')
                                            IconButton(
                                              tooltip: 'Retry in a new chat',
                                              icon: const Icon(
                                                Icons.refresh,
                                                size: 17,
                                              ),
                                              onPressed: () => _branchFrom(
                                                index - 1,
                                                prompt:
                                                    _messages[index -
                                                        1]['content'],
                                                send: true,
                                              ),
                                            ),
                                        ],
                                      ),
                                    if (!user &&
                                        (!_sending ||
                                            index != _messages.length - 1))
                                      IconButton(
                                        tooltip: 'Copy reply',
                                        icon: const Icon(
                                          Icons.copy_outlined,
                                          size: 17,
                                        ),
                                        onPressed: () async {
                                          await Clipboard.setData(
                                            ClipboardData(
                                              text: message['content']!,
                                            ),
                                          );
                                          if (context.mounted) {
                                            ScaffoldMessenger.of(
                                              context,
                                            ).showSnackBar(
                                              const SnackBar(
                                                content: Text('Reply copied'),
                                              ),
                                            );
                                          }
                                        },
                                      ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                      ),
              ),
              const SizedBox(height: 12),
              if (_interruptedReply case final String partial)
                ExpansionTile(
                  title: const Text('Interrupted reply'),
                  children: [
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 160),
                      child: SingleChildScrollView(
                        child: _replyMarkdown(partial),
                      ),
                    ),
                  ],
                ),
              if (_replyStatus case final String status)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(status),
                ),
              if (_attachment case final attachment? when !_sending)
                Align(
                  alignment: Alignment.centerLeft,
                  child: InputChip(
                    avatar: const Icon(Icons.attach_file),
                    label: Text(
                      attachment['name']!,
                      overflow: TextOverflow.ellipsis,
                    ),
                    onDeleted: () => setState(() => _attachment = null),
                  ),
                ),
              if (_attachment?['extracted'] case final String text
                  when !_sending)
                if (text.isEmpty)
                  const Text('No readable text found. Qwen cannot inspect this attachment’s visuals. Describe it in your message.')
                else
                  ExpansionTile(
                    title: Text(attachmentPreviewTitle(_attachment!['name']!)),
                    subtitle: Text('${_attachment!['name']} · ${text.runes.length} characters'),
                    children: [
                      if (isImageAttachment(_attachment!['name']!))
                        const Text('OCR can omit or misread text. Review the recognized text before sending.'),
                      const Text('Only this text is provided as attachment context. Image visuals and PDF layout are not included. Page markers can be used for citations.'),
                      ConstrainedBox(constraints: const BoxConstraints(maxHeight: 180),
                        child: SingleChildScrollView(child: SelectableText(text))),
                    ],
                  ),
              TextField(
                focusNode: _composerFocus,
                controller: _input,
                readOnly: _sending || _openingChat || _deleting,
                maxLength: 8000,
                minLines: 1,
                maxLines: 6,
                keyboardType: TextInputType.multiline,
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(
                  hintText: _attachment == null
                      ? 'Message Qwen'
                      : 'Describe the file or ask a question',
                  prefixIcon: IconButton(
                    tooltip: 'Attach file',
                    onPressed: _sending || _openingChat || _deleting
                        ? null
                        : _attachFile,
                    icon: const Icon(Icons.attach_file),
                  ),
                  counterText: '',
                  filled: true,
                  fillColor: colors.surfaceContainerLow,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                  suffixIcon: _sending
                      ? IconButton(
                          tooltip: _stopping ? 'Stopping' : 'Stop generating',
                          onPressed: _streamId == null || _stopping
                              ? null
                              : _stop,
                          icon: const Icon(Icons.stop_circle_outlined),
                        )
                      : IconButton(
                          tooltip: 'Send message',
                          onPressed: _openingChat ? null : _send,
                          icon: const Icon(Icons.arrow_upward),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Renders a selectable reply using the chat typography.
  Widget _replyMarkdown(String content) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return MarkdownBody(
      data: content,
      selectable: true,
      imageBuilder: (_, alt, _) => Text(alt ?? 'Image'),
      styleSheet: MarkdownStyleSheet.fromTheme(theme).copyWith(
        p: theme.textTheme.bodyMedium?.copyWith(fontSize: 15, height: 1.55),
        h1: theme.textTheme.headlineSmall?.copyWith(
          fontWeight: FontWeight.w700,
        ),
        h2: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
        h3: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
        blockSpacing: 12,
        code: TextStyle(
          fontFamily: Platform.isMacOS ? 'Menlo' : 'Consolas',
          fontSize: 13,
          height: 1.45,
          backgroundColor: colors.surfaceContainerHighest,
        ),
        codeblockPadding: const EdgeInsets.all(12),
        codeblockDecoration: BoxDecoration(
          color: colors.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
        ),
      ),
    );
  }

  /// Builds a settings card with an icon, heading, and content.
  Widget _settingsSection(IconData icon, String title, List<Widget> children) {
    final theme = Theme.of(context);
    return Card.outlined(
      margin: EdgeInsets.zero,
      color: theme.colorScheme.surface,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(icon, color: theme.colorScheme.primary, size: 21),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(title, style: theme.textTheme.titleMedium),
                ),
              ],
            ),
            const SizedBox(height: 14),
            ...children,
          ],
        ),
      ),
    );
  }

  /// Shows model readiness, runtime controls, and checkpoint management.
  Widget _buildSettings(bool ready) {
    final model = _model;
    final active = model?['downloading'] == true;
    final phase = model?['phase'];
    final total = (model?['total_bytes'] as num?) ?? 0;
    final received = (model?['downloaded_bytes'] as num?) ?? 0;
    final fraction = total > 0 ? (received / total).clamp(0.0, 1.0) : null;
    final canManage = model?['supported'] == true && model?['runtime'] == true;
    const phaseLabels = {
      'preparing': 'Checking model files',
      'downloading': 'Downloading from Hugging Face',
      'verifying': 'Verifying file integrity',
      'pausing': 'Pausing…',
      'paused': 'Download paused',
      'broken': 'Model needs repair',
      'failed': 'Setup interrupted',
    };
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(
          onPressed: () => setState(() => _showSettings = false),
        ),
        title: const Text('Settings'),
      ),
      backgroundColor: colors.surfaceContainerLowest,
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 820),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              _settingsSection(Icons.memory_outlined, 'Local model', [
                Text(
                  'Qwen3.8-27B',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                Text(
                  _backendOffline
                      ? 'Waiting for backend'
                      : ready
                      ? 'Verified and ready to use'
                      : phaseLabels[phase] ?? 'Setup required',
                  style: TextStyle(color: colors.primary),
                ),
                if (_checking && !_backendOffline) ...[
                  const SizedBox(height: 12),
                  const LinearProgressIndicator(),
                ],
              ]),
              const SizedBox(height: 16),
              _settingsSection(Icons.dns_outlined, 'Backend runtime', [
                if (_backendOffline)
                  _backendRecovery()
                else ...[
                  Text(model == null ? 'Checking connection…' : 'Connected'),
                  if (Platform.isMacOS && model != null) ...[
                    const SizedBox(height: 12),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton.icon(
                        onPressed:
                            _checking || _stoppingRuntime || _sending || active
                            ? null
                            : _stopRuntime,
                        icon: const Icon(Icons.stop_circle_outlined),
                        label: Text(
                          _stoppingRuntime
                              ? 'Stopping runtime…'
                              : 'Stop runtime',
                        ),
                      ),
                    ),
                  ],
                ],
                if (_error case final String error) ...[
                  const SizedBox(height: 8),
                  Text(error, style: TextStyle(color: colors.error)),
                ],
              ]),
              const SizedBox(height: 16),
              _settingsSection(Icons.folder_outlined, 'Model files', [
                if (model?['directory'] case final String directory) ...[
                  Text(
                    'Storage location',
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                  const SizedBox(height: 4),
                  SelectableText(directory),
                  const SizedBox(height: 12),
                ],
                if (!ready) ...[
                  const SizedBox(height: 12),
                  const Text(
                    'Download the 4-bit model (about 16 GB) to chat on this Mac.',
                  ),
                  if (model?['supported'] == false)
                    const Text(
                      'This inference runtime requires an Apple silicon Mac.',
                    )
                  else if (model?['runtime'] == false)
                    const Text(
                      'Install the Python dependencies from the setup guide.',
                    ),
                  if (model?['file'] case final String file) Text(file),
                  if (total > 0 && !ready) ...[
                    const SizedBox(height: 8),
                    LinearProgressIndicator(value: fraction),
                    Text(
                      '${_size(received)} of ${_size(total)} '
                      '(${(fraction! * 100).toStringAsFixed(1)}%) · '
                      '${model?['completed_files']} of ${model?['total_files']} files on disk',
                    ),
                  ],
                  if (!_backendOffline &&
                      phase == 'downloading' &&
                      _downloadBytesPerSecond != null)
                    Text('${_size(_downloadBytesPerSecond!)}/s'),
                  if (model?['error'] case final String error)
                    Text(error, style: TextStyle(color: colors.error)),
                ],
                const SizedBox(height: 12),
                if (!_backendOffline)
                  Wrap(
                    spacing: 12,
                    runSpacing: 8,
                    children: [
                      if (canManage && active)
                        OutlinedButton(
                          onPressed: _checking || phase == 'pausing'
                              ? null
                              : () => _refresh(action: 'pause'),
                          child: const Text('Pause'),
                        ),
                      if (canManage && !active && !ready)
                        FilledButton(
                          onPressed: _checking
                              ? null
                              : () => _refresh(action: 'resume'),
                          child: Text(switch (phase) {
                            'paused' => 'Resume download',
                            'broken' || 'failed' => 'Repair / resume',
                            _ => 'Download local model',
                          }),
                        ),
                      if (canManage && !active)
                        TextButton(
                          onPressed: _checking || _sending
                              ? null
                              : () => _refresh(action: 'verify'),
                          child: const Text('Verify files'),
                        ),
                      if (!active && !ready)
                        TextButton(
                          onPressed: _checking ? null : _refresh,
                          child: const Text('Check setup'),
                        ),
                    ],
                  ),
              ]),
              const SizedBox(height: 16),
              _settingsSection(Icons.history, 'Conversation memory', [
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Use other conversations'),
                  subtitle: const Text(
                    'Use related messages from other chats in the same project.',
                  ),
                  value: _recall,
                  onChanged: _sending ? null : _setRecall,
                ),
              ]),
            ],
          ),
        ),
      ),
    );
  }
}
