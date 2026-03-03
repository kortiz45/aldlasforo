(() => {
    const STORAGE_KEY = "mb_devtools_guard";
    const QUERY_KEY = "devtools_guard";
    const CHECK_INTERVAL_MS = 1000;
    const RELOAD_INTERVAL_MS = 1000;
    const DEVTOOLS_SIZE_THRESHOLD = 170;
    const DEBUGGER_DELAY_THRESHOLD_MS = 120;

    function parseToggle(rawValue) {
        if (rawValue === null || rawValue === undefined) return null;
        const value = String(rawValue).trim().toLowerCase();
        if (["1", "true", "on", "yes", "enable", "enabled"].includes(value)) return true;
        if (["0", "false", "off", "no", "disable", "disabled"].includes(value)) return false;
        return null;
    }

    function isLocalEnvironment() {
        const host = String(window.location.hostname || "").toLowerCase();
        return (
            window.location.protocol === "file:" ||
            host === "localhost" ||
            host === "127.0.0.1" ||
            host === "::1"
        );
    }

    function resolveGuardEnabled() {
        let queryToggle = null;
        try {
            queryToggle = parseToggle(new URLSearchParams(window.location.search).get(QUERY_KEY));
        } catch (_err) {
            queryToggle = null;
        }
        if (queryToggle !== null) return queryToggle;

        let storedToggle = null;
        try {
            storedToggle = parseToggle(window.localStorage.getItem(STORAGE_KEY));
        } catch (_err) {
            storedToggle = null;
        }
        if (storedToggle !== null) return storedToggle;

        if (typeof window.__ENABLE_DEVTOOLS_GUARD__ === "boolean") {
            return window.__ENABLE_DEVTOOLS_GUARD__;
        }

        return !isLocalEnvironment();
    }

    function setDevtoolsGuardEnabled(enabled) {
        try {
            window.localStorage.setItem(STORAGE_KEY, enabled ? "1" : "0");
        } catch (_err) {
            // ignore storage errors
        }
    }

    window.setDevtoolsGuardEnabled = setDevtoolsGuardEnabled;

    if (!resolveGuardEnabled()) {
        return;
    }

    let reloadLoopStarted = false;

    function isDevtoolsOpenByViewport() {
        const widthDiff = Math.abs(window.outerWidth - window.innerWidth);
        const heightDiff = Math.abs(window.outerHeight - window.innerHeight);
        return widthDiff > DEVTOOLS_SIZE_THRESHOLD || heightDiff > DEVTOOLS_SIZE_THRESHOLD;
    }

    function isDevtoolsOpenByDebuggerPause() {
        const start = performance.now();
        // eslint-disable-next-line no-debugger
        debugger;
        return (performance.now() - start) > DEBUGGER_DELAY_THRESHOLD_MS;
    }

    function isDevtoolsOpen() {
        if (isDevtoolsOpenByViewport()) {
            return true;
        }
        try {
            return isDevtoolsOpenByDebuggerPause();
        } catch (_err) {
            return false;
        }
    }

    function forceReload() {
        try {
            const nextUrl = new URL(window.location.href);
            nextUrl.searchParams.set("_rt", String(Date.now()));
            window.location.replace(nextUrl.toString());
        } catch (_err) {
            window.location.reload();
        }
    }

    function startReloadLoop() {
        if (reloadLoopStarted) return;
        reloadLoopStarted = true;
        forceReload();
        setInterval(forceReload, RELOAD_INTERVAL_MS);
    }

    setInterval(() => {
        if (isDevtoolsOpen()) {
            startReloadLoop();
        }
    }, CHECK_INTERVAL_MS);

    window.addEventListener(
        "resize",
        () => {
            if (isDevtoolsOpen()) {
                startReloadLoop();
            }
        },
        { passive: true }
    );
})();
