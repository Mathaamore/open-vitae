import AppKit
import WebKit

@MainActor
final class CandidaturesApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var backend: Process?
    var base: URL?
    var workspace: URL?
    var suggestedWorkspace: URL?
    var scopedWorkspace: URL?
    var output: Pipe?
    var startupData = Data()
    var loading: NSTextField!
    var downloads: [WKDownload] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        makeMenu()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1360, height: 900), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Open Vitæ"
        window.appearance = NSAppearance(named: .aqua)
        window.titlebarAppearsTransparent = true
        window.titlebarSeparatorStyle = .none
        window.backgroundColor = NSColor(calibratedRed: 0.95, green: 0.96, blue: 0.97, alpha: 1)
        window.minSize = NSSize(width: 840, height: 580)
        window.setFrameAutosaveName("CandidaturesMainWindow")
        window.center()
        window.delegate = self
        let configuration = WKWebViewConfiguration()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = true
        web = WKWebView(frame: window.contentView!.bounds, configuration: configuration)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        web.uiDelegate = self
        web.isHidden = true
        window.contentView!.addSubview(web)
        loading = NSTextField(labelWithString: "Ouverture de ton espace…")
        loading.textColor = .secondaryLabelColor
        loading.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(loading)
        NSLayoutConstraint.activate([loading.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor), loading.centerYAnchor.constraint(equalTo: window.contentView!.centerYAnchor)])
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        let saved = UserDefaults.standard.string(forKey: "Workspace")
        let seed = Bundle.main.url(forResource: "workspace", withExtension: "json").flatMap { try? Data(contentsOf: $0) }.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: String] }?["path"]
        suggestedWorkspace = (saved ?? seed).map { URL(fileURLWithPath: $0) }
        if let data = UserDefaults.standard.data(forKey: "WorkspaceBookmark") {
            var stale = false
            if let url = try? URL(resolvingBookmarkData: data, options: [.withSecurityScope], relativeTo: nil, bookmarkDataIsStale: &stale), !stale {
                launch(url)
                return
            }
        }
        if let seed, FileManager.default.fileExists(atPath: seed + "/data/agent.sqlite3") {
            chooseWorkspace()
        } else {
            let local = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!.appendingPathComponent("Candidatures", isDirectory: true)
            do {
                try FileManager.default.createDirectory(at: local, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
                launch(local)
            } catch { self.error("L’espace local n’a pas pu être créé.") }
        }
    }

    func makeMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem(); menu.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "À propos d’Open Vitæ", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quitter Open Vitæ", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let fileItem = NSMenuItem(); menu.addItem(fileItem)
        let fileMenu = NSMenu(title: "Fichier"); fileItem.submenu = fileMenu
        fileMenu.addItem(withTitle: "Choisir un espace de travail…", action: #selector(changeWorkspace), keyEquivalent: "o")
        fileMenu.addItem(withTitle: "Afficher l’espace dans le Finder", action: #selector(showWorkspace), keyEquivalent: "")
        let editItem = NSMenuItem(); menu.addItem(editItem)
        let editMenu = NSMenu(title: "Édition"); editItem.submenu = editMenu
        for (title, action, key) in [("Annuler", "undo:", "z"), ("Rétablir", "redo:", "Z"), ("Couper", "cut:", "x"), ("Copier", "copy:", "c"), ("Coller", "paste:", "v"), ("Tout sélectionner", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        let viewItem = NSMenuItem(); menu.addItem(viewItem)
        let viewMenu = NSMenu(title: "Présentation"); viewItem.submenu = viewMenu
        viewMenu.addItem(withTitle: "Recharger", action: #selector(reload), keyEquivalent: "r")
        viewMenu.addItem(withTitle: "Agrandir", action: #selector(zoomIn), keyEquivalent: "+")
        viewMenu.addItem(withTitle: "Réduire", action: #selector(zoomOut), keyEquivalent: "-")
        viewMenu.addItem(withTitle: "Taille réelle", action: #selector(resetZoom), keyEquivalent: "0")
        for submenu in [appMenu, fileMenu, viewMenu] { for item in submenu.items { if item.action != #selector(NSApplication.terminate(_:)) { item.target = self } } }
        NSApp.mainMenu = menu
    }

    @objc func about() { NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "Open Vitæ", .applicationVersion: "0.3.1", .credits: NSAttributedString(string: "Ton espace local pour préparer la suite.\nLes candidatures restent envoyées manuellement.")]) }
    @objc func showWorkspace() { if let workspace { NSWorkspace.shared.open(workspace) } }
    @objc func zoomIn() { web.pageZoom = min(1.6, web.pageZoom + 0.1) }
    @objc func zoomOut() { web.pageZoom = max(0.8, web.pageZoom - 0.1) }
    @objc func resetZoom() { web.pageZoom = 1 }
    @objc func reload() { guardEdits { self.web.reload() } }
    @objc func changeWorkspace() { guardEdits { self.chooseWorkspace() } }

    func guardEdits(_ action: @escaping () -> Void, cancel: @escaping () -> Void = {}) {
        if web.isHidden || base == nil { action(); return }
        web.evaluateJavaScript("(typeof dirty !== 'undefined' && dirty) || window.profileDirty === true") { value, _ in
            if value as? Bool == true {
                let alert = NSAlert(); alert.messageText = "Des modifications ne sont pas enregistrées."
                alert.informativeText = "Reviens au dossier pour les enregistrer, ou quitte en les abandonnant."
                alert.addButton(withTitle: "Revenir au dossier"); alert.addButton(withTitle: "Abandonner les modifications")
                alert.beginSheetModal(for: self.window) { if $0 == .alertSecondButtonReturn { action() } else { cancel() } }
            } else { action() }
        }
    }

    func chooseWorkspace() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.message = "Choisis le dossier de ton projet contenant data/agent.sqlite3. Tes données restent dans ce dossier."
        panel.prompt = "Ouvrir cet espace"
        panel.directoryURL = self.workspace ?? self.suggestedWorkspace
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let url = panel.url else { if self.backend == nil { self.loading.stringValue = "Choisis ton espace depuis le menu Fichier." }; return }
            guard FileManager.default.fileExists(atPath: url.appendingPathComponent("data/agent.sqlite3").path) else { self.error("Ce dossier ne contient pas d’espace de candidatures existant."); return }
            UserDefaults.standard.set(url.path, forKey: "Workspace")
            if let bookmark = try? url.bookmarkData(options: [.withSecurityScope], includingResourceValuesForKeys: nil, relativeTo: nil) {
                UserDefaults.standard.set(bookmark, forKey: "WorkspaceBookmark")
            }
            self.launch(url)
        }
    }

    func launch(_ root: URL) {
        stop()
        if root.startAccessingSecurityScopedResource() { scopedWorkspace = root }
        workspace = root; startupData = Data(); base = nil; web.isHidden = true
        loading.stringValue = "Ouverture de ton espace…"; loading.isHidden = false
        let process = Process(); backend = process
        let resources = Bundle.main.resourceURL!
        process.executableURL = resources.appendingPathComponent("service/candidatures-service")
        process.arguments = [root.path]
        var environment = ProcessInfo.processInfo.environment
        environment["JOB_AGENT_CODEX"] = resources.appendingPathComponent("codex").path
        environment["JOB_AGENT_ROOT"] = root.path
        environment["PLAYWRIGHT_BROWSERS_PATH"] = resources.appendingPathComponent("browsers").path
        process.environment = environment
        let pipe = Pipe(); output = pipe; process.standardOutput = pipe
        let log = root.appendingPathComponent("data/desktop-service.log")
        FileManager.default.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600])
        process.standardError = (try? FileHandle(forWritingTo: log)) ?? FileHandle.nullDevice
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            DispatchQueue.main.async {
                guard self.backend === process, !data.isEmpty else { return }
                self.startupData.append(data)
                if self.base == nil, let line = String(data: self.startupData, encoding: .utf8)?.components(separatedBy: "\n").first,
                   let json = line.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: json) as? [String: Int], let port = value["port"], port > 0, port < 65536 {
                    let url = URL(string: "http://127.0.0.1:\(port)")!
                    self.base = url; self.waitForService(url, attempts: 60)
                }
            }
        }
        process.terminationHandler = { _ in DispatchQueue.main.async { if self.backend === process { self.loading.isHidden = false; self.loading.stringValue = "Le service local s’est arrêté. Relance Open Vitæ." } } }
        do { try process.run() } catch { self.error("Impossible de démarrer le service local.") }
    }

    func waitForService(_ url: URL, attempts: Int) {
        URLSession.shared.dataTask(with: URLRequest(url: url.appendingPathComponent("api/session"), timeoutInterval: 2)) { _, response, _ in
            DispatchQueue.main.async {
                guard self.base == url else { return }
                if (response as? HTTPURLResponse)?.statusCode == 200 {
                    self.web.load(URLRequest(url: url))
                } else if attempts > 0 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.waitForService(url, attempts: attempts - 1) }
                } else { self.error("Le service local ne répond pas. Relance l’application.") }
            }
        }.resume()
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { loading.isHidden = true; web.isHidden = false }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { self.error("La page locale n’a pas pu être chargée. Utilise Présentation → Recharger.") }
    func isLocal(_ url: URL) -> Bool { url.scheme == base?.scheme && url.host == base?.host && url.port == base?.port }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { decisionHandler(.cancel); return }
        if isLocal(url) { decisionHandler(action.shouldPerformDownload ? .download : .allow) }
        else if ["https", "http", "mailto"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url); decisionHandler(.cancel) }
        else { decisionHandler(.cancel) }
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url, ["https", "http", "mailto"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        return nil
    }
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let attachment = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition")?.lowercased().contains("attachment") == true
        decisionHandler(attachment || !response.canShowMIMEType ? .download : .allow)
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self; downloads.append(download) }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self; downloads.append(download) }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel(); panel.nameFieldStringValue = (suggestedFilename as NSString).lastPathComponent
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.url : nil) }
    }
    func downloadDidFinish(_ download: WKDownload) { downloads.removeAll { $0 === download } }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) { downloads.removeAll { $0 === download }; if (error as NSError).code != NSURLErrorCancelled { self.error("Le téléchargement n’a pas abouti. Réessaie.") } }
    func error(_ text: String) { let alert = NSAlert(); alert.messageText = text; alert.beginSheetModal(for: window) }
    func stop() {
        let process = backend; backend = nil; base = nil
        if let process, process.isRunning {
            kill(-process.processIdentifier, SIGTERM); process.terminate()
            let deadline = Date().addingTimeInterval(0.5)
            while process.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if process.isRunning { kill(-process.processIdentifier, SIGKILL); kill(process.processIdentifier, SIGKILL) }
            // Reaping stays with Foundation; never block the UI on a stopped helper.
        }
        scopedWorkspace?.stopAccessingSecurityScopedResource(); scopedWorkspace = nil
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { NSApp.terminate(nil); return false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply { if web.isHidden || base == nil { return .terminateNow }; guardEdits({ NSApp.reply(toApplicationShouldTerminate: true) }, cancel: { NSApp.reply(toApplicationShouldTerminate: false) }); return .terminateLater }
    func applicationWillTerminate(_ notification: Notification) { stop() }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { window.makeKeyAndOrderFront(nil); return true }
}

@main
struct Launcher {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = CandidaturesApp()
        app.delegate = delegate
        app.run()
    }
}
