# Synthetic RT identities only. Existing passwords, ACLs and disabled flags are preserved.
use strict;
use warnings;
use JSON::PP qw(encode_json decode_json);
use RT;
RT->LoadConfig; RT->Init;
die "Unexpected RT database" unless RT->Config->Get('DatabaseHost') eq 'rt-db' && $ENV{BEARINGS_RT_LAB} eq '1';

sub read_file { open my $fh, '<', $_[0] or die "Missing private input"; local $/; my $v = <$fh>; close $fh; $v =~ s/\r?\n\z//; return $v; }
sub private_write {
    my ($path,$value,$uid) = @_;
    open my $fh, '>', $path or die "Cannot save private RT output";
    print $fh $value; close $fh; chmod 0600, $path; chown $uid,0,$path;
}
sub user {
    my ($name,$human) = @_;
    my $user = RT::User->new(RT->SystemUser); $user->Load($name);
    my $created = !$user->Id;
    my $marker = "bearings-rt-lab:v1:$name";
    if ($created) {
        my ($ok,$msg) = $user->Create(Name=>$name, RealName=>"$name (SYNTHETIC)", Comments=>$marker,
            EmailAddress=>"$name\@example.invalid", Privileged=>1,
            Password=>$human ? read_file('/run/rt/demo_password') : undef);
        die "Cannot create synthetic RT account" unless $ok;
    } else { die "Reserved RT account identity differs; preserved" unless $user->Comments eq $marker; }
    return ($user,$created);
}
sub queue {
    my ($name) = @_;
    my $queue = RT::Queue->new(RT->SystemUser); $queue->Load($name);
    my $marker = "bearings-rt-lab:v1:$name (SYNTHETIC, local mbox only)";
    if (!$queue->Id) { my ($ok)=$queue->Create(Name=>$name,Description=>$marker); die "Cannot create RT queue" unless $ok; }
    else { die "Reserved RT queue identity differs; preserved" unless $queue->Description eq $marker; }
    return $queue;
}
my $retained='/var/lib/request-tracker5/bearings-lab.json';
my $old=-e $retained ? decode_json(read_file($retained)) : undef;
my %queues; my %probe; my %users; my %services;
for my $kind ('company','circl') {
    my $human_name=$kind eq 'company' ? 'company-admin' : 'circl-analyst';
    if ($old) {
        my $prior_queue=RT::Queue->new(RT->SystemUser);$prior_queue->Load($old->{queues}{$kind});
        my $prior_user=RT::User->new(RT->SystemUser);$prior_user->Load($old->{users}{$kind});
        die "Retained RT account/queue renamed or missing; preserved without recreation"
            unless $prior_queue->Id && $prior_queue->Name eq "Bearings-$kind" && $prior_user->Id && $prior_user->Name eq $human_name;
    }
    my $queue = queue("Bearings-$kind"); $queues{$kind} = $queue->Id;
    my ($human,$new) = user($human_name,1);
    $users{$kind}=$human->Id;
    if ($new) {
        for my $right (qw(SeeQueue ShowTicket ShowTicketComments CreateTicket ModifyTicket ReplyToTicket CommentOnTicket OwnTicket TakeTicket)) {
            my ($ok)=$human->PrincipalObj->GrantRight(Object=>$queue,Right=>$right); die "Cannot grant synthetic queue right" unless $ok;
        }
    }
    my $keypath='/run/bearings/secrets/RT_BUNDLED_'.uc($kind).'_TOKEN';
    if (-e $keypath) {
        my ($prior)=RT::Authen::Token->UserForAuthString(read_file($keypath));
        die "Retained RT bridge disabled, renamed or token revoked; preserved" unless $prior && $prior->Name eq "bearings-$kind-bridge";
    }
    my ($service,$service_new)=user("bearings-$kind-bridge",0);
    $services{$kind}=$service->Id;
    if ($service_new) {
        for my $right (qw(SeeQueue ShowTicket ShowTicketComments CreateTicket)) {
            my ($ok)=$service->PrincipalObj->GrantRight(Object=>$queue,Right=>$right); die "Cannot grant scoped bridge right" unless $ok;
        }
    }
    my $appuid=read_file('/run/bearings/secrets/app_uid');
    if (-e $keypath) {
        my ($valid)=RT::Authen::Token->UserForAuthString(read_file($keypath));
        die "RT bridge token differs or was revoked; preserved" unless $valid && $valid->Id == $service->Id;
    } else {
        my $tokens=RT::AuthTokens->new(RT->SystemUser);$tokens->Limit(FIELD=>'Owner',VALUE=>$service->Id);
        die "RT bridge token exists without retained key; recover without automatic rotation" if $tokens->Count;
        my $token=RT::AuthToken->new(RT->SystemUser);
        my ($id,$msg,$raw)=$token->Create(Owner=>$service->Id,Description=>'Bearings isolated lab');
        die "Cannot create scoped RT bridge token" unless $id;
        private_write($keypath,$raw."\n",$appuid);
    }
    my $subject="Bearings $kind isolation probe (SYNTHETIC)";
    my $ticket;
    if ($old && $old->{probe_tickets}{$kind}) {
        $ticket=RT::Ticket->new(RT->SystemUser);$ticket->Load($old->{probe_tickets}{$kind});
        die "Retained RT probe identity changed; no replacement created" unless $ticket->Id && $ticket->Queue == $queue->Id;
    } else {
        my $tickets=RT::Tickets->new(RT->SystemUser);
        $tickets->Limit(FIELD=>'Queue',VALUE=>$queue->Id);$tickets->Limit(FIELD=>'Subject',VALUE=>$subject);
        $ticket=$tickets->First;
    }
    if (!$ticket) { $ticket=RT::Ticket->new(RT->SystemUser); my ($id)=$ticket->Create(Queue=>$queue->Id,Subject=>$subject,Creator=>RT->SystemUser->Id); die "Cannot create synthetic probe" unless $id; }
    $probe{$kind}=$ticket->Id;
}
my $config=decode_json(read_file('/run/rt/config.json'));
my $metadata={%$config,queues=>\%queues,probe_tickets=>\%probe,users=>\%users,services=>\%services,version=>$RT::VERSION};
if (-e $retained) {
    my $old=decode_json(read_file($retained));
    for my $kind ('company','circl') { die "Retained RT identity changed" unless $old->{queues}{$kind}==$queues{$kind} && $old->{users}{$kind}==$users{$kind}; }
}
private_write($retained,encode_json($metadata)."\n",33);
private_write('/run/bearings/secrets/rt.json',encode_json($metadata)."\n",read_file('/run/bearings/secrets/app_uid'));
print "Scoped RT lab fixture metadata prepared without logging keys.\n";
