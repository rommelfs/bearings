use strict;
use warnings;
use JSON::PP qw(decode_json);
use RT;
RT->LoadConfig; RT->Init;
die "Not the isolated RT lab" unless $ENV{BEARINGS_RT_LAB} eq '1' && RT->Config->Get('DatabaseHost') eq 'rt-db';
die "RT mail must remain local" unless RT->Config->Get('MailCommand') eq 'mbox';
open my $fh,'<','/var/lib/request-tracker5/bearings-lab.json' or die; local $/;my $data=decode_json(<$fh>);close $fh;
for my $kind ('company','circl') {
    my $other=$kind eq 'company' ? 'circl' : 'company';
    my $user=RT::CurrentUser->new; $user->Load($data->{users}{$kind});
    die "Expected scoped human" unless $user->Id && !$user->HasRight(Object=>RT->System,Right=>'SuperUser');
    my $own=RT::Ticket->new($user);$own->Load($data->{probe_tickets}{$kind});
    my $foreign=RT::Ticket->new($user);$foreign->Load($data->{probe_tickets}{$other});
    die "Own probe denied" unless $own->CurrentUserHasRight('ShowTicket');
    die "Foreign probe visible" if $foreign->CurrentUserHasRight('ShowTicket');
}
print "Verified real RT scoped human queue access, foreign-queue denial and local-only mbox mail.\n";
