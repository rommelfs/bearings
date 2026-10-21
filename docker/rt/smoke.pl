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

if (-e '/var/lib/request-tracker5/bearings-rtir.json') {
    open my $rf,'<','/var/lib/request-tracker5/bearings-rtir.json' or die;my $rtir=decode_json(<$rf>);close $rf;
    die 'Expected RTIR version' unless $rtir->{version} eq '5.0.10';
    my $company=RT::CurrentUser->new;$company->Load($data->{users}{company});
    my $circl=RT::CurrentUser->new;$circl->Load($data->{users}{circl});
    for my $kind (keys %{$rtir->{queues}}) {
        my $q=RT::Queue->new($company);$q->Load($rtir->{queues}{$kind});
        for my $right (qw(SeeQueue ShowTicket CreateTicket ReplyToTicket)) {
            die 'Company has RTIR rights' if $company->HasRight(Object=>$q,Right=>$right);
        }
        my $cq=RT::Queue->new($circl);$cq->Load($rtir->{queues}{$kind});
        die 'CIRCL RTIR queue access denied' unless $circl->HasRight(Object=>$cq,Right=>'SeeQueue');
    }
    print "Verified native RTIR 5.0.10 CIRCL queue rights and company denial across all four lifecycles.\n";
}
