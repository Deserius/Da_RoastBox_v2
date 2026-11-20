(function () {
  var current = new URL(window.location.href);
  var state = current.searchParams.get("state") || "";
  var result = {
    type: "roastbox-google-auth-result",
    state: state,
    code: current.searchParams.get("code") || "",
    error: current.searchParams.get("error") || ""
  };
  // Google redirects straight back here with ?code&state (no broker in
  // between), so the popup/redirect mode travels as a suffix on our own
  // opaque state value instead of a separate query param - the redirect_uri
  // registered in Google Cloud Console must stay an exact, stable string.
  var mode = state.slice(state.lastIndexOf(".") + 1);
  // Do this before opening the main app or running any third-party scripts.
  window.history.replaceState(null, "", current.pathname);
  var status = document.getElementById("status");
  var back = document.getElementById("return");
  if (mode === "popup") {
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage(result, window.location.origin);
      status.textContent = "You can close this window and return to Da RoastBox.";
      window.setTimeout(function () { window.close(); }, 100);
    } else {
      status.textContent = "Couldn't return to the original app window. Open Da RoastBox in a new tab and try signing in again.";
      back.hidden = false;
    }
  } else if (mode === "redirect") {
    try {
      window.sessionStorage.setItem("roastbox_google_auth_result", JSON.stringify(result));
      window.location.replace("/auth/callback");
    } catch (e) {
      status.textContent = "Your browser blocked sign-in storage. Allow site storage and try again.";
      back.hidden = false;
    }
  } else {
    status.textContent = "This sign-in link is invalid or expired. Please start again.";
    back.hidden = false;
  }
})();
