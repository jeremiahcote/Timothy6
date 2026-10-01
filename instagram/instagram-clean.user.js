// ==UserScript==
// @name         Instagram: no Reels, no Search
// @description  Leaves the home feed, profiles and DMs. Removes the Reels feed and Search/Explore.
// @match        https://www.instagram.com/*
// @match        https://instagram.com/*
// @run-at       document-start
// @version      1.0
// ==/UserScript==

(function () {
  // /reels/ is the endless Reels feed and /explore/ is Search + Explore.
  // /reel/<id> (singular) is one reel, e.g. sent by a friend, and stays allowed.
  const BLOCKED = /^\/(reels|explore)(\/|$)/;

  const style = document.createElement("style");
  style.textContent = `
    a[href^="/reels/"], a[href^="/explore/"],
    a[href="/reels"], a[href="/explore"],
    input[placeholder="Search"], [aria-label="Search"], [aria-label="Search input"] {
      display: none !important;
    }
  `;
  (document.head || document.documentElement).appendChild(style);

  function enforce() {
    if (BLOCKED.test(location.pathname)) location.replace("/");
  }

  // Instagram navigates without page loads, so keep checking the address.
  enforce();
  setInterval(enforce, 250);
})();
