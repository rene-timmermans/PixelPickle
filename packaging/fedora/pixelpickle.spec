Name:           pixelpickle
Version:        %{pp_version}
Release:        1%{?dist}
Summary:        Fotobewerker voor Linux met een begrijpelijke en vertrouwde indeling van de gereedschappen
License:        GPL-3.0-or-later
URL:            https://github.com/rene-timmermans/pixelpickle
Source0:        pixelpickle-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.11
Requires:       python3-pyside6
Requires:       python3-numpy
Requires:       python3-pillow
Recommends:     google-noto-sans-fonts
# Python bestanden staan buiten site-packages; geen automatische bytecode/afhankelijkheden afleiden
%global __brp_python_bytecompile %{nil}
%global __requires_exclude_from ^%{_datadir}/pixelpickle/.*$

%description
PixelPickle is een fotobewerker voor Linux met een begrijpelijke en vertrouwde indeling van
menu's, gereedschappen en sneltoetsen: lagen, maskers, aanpassingslagen, selecties, retoucheren
en ruim 140 effecten.

%prep
%setup -q

%install
sh packaging/stage.sh %{buildroot}

%files
%license LICENSE
%{_bindir}/pixelpickle
%{_datadir}/pixelpickle/
%{_datadir}/applications/pixelpickle.desktop
%{_datadir}/icons/hicolor/*/apps/pixelpickle.png
%{_docdir}/pixelpickle/README.md
%{_datadir}/licenses/pixelpickle/LICENSE
