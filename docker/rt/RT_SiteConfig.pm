use JSON::PP qw(decode_json);
sub lab_file {
    my ($path) = @_;
    open my $fh, '<', $path or die "Cannot read RT lab input";
    local $/; my $value = <$fh>; close $fh; $value =~ s/\r?\n\z//; return $value;
}
my $lab = decode_json(lab_file('/run/rt/config.json'));
my $recovery = $ENV{BEARINGS_RT_RECOVERY} ? 1 : 0;
Set($rtname, 'bearings-synthetic-rt');
Set($Organization, 'bearings.invalid');
Set($DatabaseType, 'Pg');
Set($DatabaseHost, 'rt-db');
Set($DatabasePort, 5432);
Set($DatabaseName, 'rt');
Set($DatabaseUser, 'rt');
Set($DatabasePassword, lab_file('/run/rt/db_password'));
Set($WebDomain, 'localhost');
Set($WebPort, $recovery ? $lab->{recovery_port} : $lab->{port});
Set($WebPath, '');
Set($WebBaseURL, 'https://localhost:' . ($recovery ? $lab->{recovery_port} : $lab->{port}));
Set($WebURL, RT->Config->Get('WebBaseURL') . '/');
Set($WebRemoteUserAuth, $ENV{BEARINGS_RT_SSO} && !$recovery ? 1 : 0);
Set($WebRemoteUserContinuous, 1);
Set($WebRemoteUserAutocreate, 0);
Set($WebRemoteUserGecos, 0);
Set($WebFallbackToRTLogin, $recovery || !$ENV{BEARINGS_RT_SSO} ? 1 : 0);
Set(%WebRemoteUserAdditionalMapping, ());
Set($WebSecureCookies, 1);
Set($WebHttpOnlyCookies, 1);
Set($WebSameSiteCookies, 'Lax');
Set($AutoLogoff, 30);
# RT's documented local-only mail mode; the installed MTA has no remote destination.
Set($MailCommand, 'mbox');
Set($LogToSTDERR, 'warning');
Set($LogToSyslog, undef);
Set($LogToFile, undef);
Set($RestrictReferrer, 1);
Set(@ReferrerWhitelist, 'localhost:' . $lab->{port}, 'localhost:' . $lab->{recovery_port});
1;
