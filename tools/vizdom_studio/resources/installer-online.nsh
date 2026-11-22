; installer-online.nsh - the online installer's NSIS include (npm run dist:online).
; Same pages as the full installer, plus "Text recognition", which downloads
; EasyOCR and PyTorch instead of shipping them (see installer.nsh).
!define VIZDOM_ONLINE
!include "${__FILEDIR__}\installer.nsh"
