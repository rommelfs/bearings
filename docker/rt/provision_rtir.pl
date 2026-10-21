# Only the explicitly enabled synthetic lab. Never run against an external RTIR database.
use strict;
use warnings;
use JSON::PP qw(decode_json encode_json);
use RT;
RT->LoadConfig; RT->Init;
require RT::IR;
die 'Not the isolated RTIR lab' unless $ENV{BEARINGS_RT_LAB} eq '1' && RT->Config->Get('DatabaseHost') eq 'rt-db';
sub read_file { open my $f,'<',$_[0] or die 'Missing private input';local $/;my $v=<$f>;close $f;$v =~ s/\r?\n\z//;return $v; }
sub write_private { my($path,$value,$uid)=@_;open my $f,'>',$path or die;print $f $value;close $f;chmod 0600,$path;chown $uid,0,$path; }
my $marker='/var/lib/request-tracker5/bearings-rtir.json';
my $old=-e $marker ? decode_json(read_file($marker)) : undef;
die "RTIR version changed; explicit upgrade required" if $old && $old->{version} ne $RT::IR::VERSION;
my %queues;
for my $pair (['incident','Incidents','incidents'],['investigation','Investigations','investigations'],['report','Incident Reports','incident_reports'],['countermeasure','Countermeasures','countermeasures']) {
    my($kind,$name,$lifecycle)=@$pair;
    my $q=RT::Queue->new(RT->SystemUser);$q->Load($name);
    die 'Missing or changed RTIR lifecycle/queue' unless $q->Id && $q->Lifecycle eq $lifecycle;
    die 'Retained RTIR identity changed' if $old && $old->{queues}{$kind} != $q->Id;
    $queues{$kind}=$q->Id;
    # Remove only the upstream initial public submission/reply grants at first installation.
    if (!$old) {
        my $all=RT::Group->new(RT->SystemUser);$all->LoadSystemInternalGroup('Everyone');
        for my $right (qw(CreateTicket ReplyToTicket)) { $all->PrincipalObj->RevokeRight(Object=>$q,Right=>$right); }
    }
}
my $human=RT::User->new(RT->SystemUser);$human->Load('circl-analyst');die 'Missing CIRCL human' unless $human->Id;
if (!$old) {
    # Dedicated grants, not DutyTeam membership: no accidental access to other RTIR installations.
    for my $id (values %queues) { my $q=RT::Queue->new(RT->SystemUser);$q->Load($id);
        for my $right (qw(SeeQueue ShowTicket ShowTicketComments CreateTicket ModifyTicket OwnTicket TakeTicket CommentOnTicket ReplyToTicket)) {
            my($ok)=$human->PrincipalObj->GrantRight(Object=>$q,Right=>$right);die 'Cannot grant CIRCL RTIR right' unless $ok;
        }
    }
}
my $bridge=RT::User->new(RT->SystemUser);$bridge->Load('bearings-rtir-bridge');
if (!$bridge->Id) {
    die 'Retained RTIR bridge missing; not recreated' if $old;
    my($ok)=$bridge->Create(Name=>'bearings-rtir-bridge',Privileged=>1,Comments=>'bearings-rtir-lab:v1');die 'Cannot create RTIR bridge' unless $ok;
    for my $kind ('incident','investigation') {
        my $q=RT::Queue->new(RT->SystemUser);$q->Load($queues{$kind});
        for my $right (qw(SeeQueue ShowTicket ShowTicketComments CreateTicket ModifyTicket)) {
            my($ok)=$bridge->PrincipalObj->GrantRight(Object=>$q,Right=>$right);die 'Cannot grant RTIR bridge right' unless $ok;
        }
    }
}
die 'RTIR bridge identity changed' unless $bridge->Comments eq 'bearings-rtir-lab:v1' && (!$old || $bridge->Id == $old->{bridge});
my $keypath='/run/bearings/secrets/RT_BUNDLED_RTIR_TOKEN';
my $uid=read_file('/run/bearings/secrets/app_uid');
if (-e $keypath) { my($u)=RT::Authen::Token->UserForAuthString(read_file($keypath));die 'RTIR key revoked/disabled; preserved' unless $u && $u->Id==$bridge->Id; }
else {
    my $tokens=RT::AuthTokens->new(RT->SystemUser);$tokens->Limit(FIELD=>'Owner',VALUE=>$bridge->Id);
    die 'RTIR token missing; recover without rotation' if $old || $tokens->Count;
    my $token=RT::AuthToken->new(RT->SystemUser);my($id,$msg,$raw)=$token->Create(Owner=>$bridge->Id,Description=>'Bearings isolated RTIR lab');die 'Cannot create RTIR key' unless $id;
    write_private($keypath,$raw."\n",$uid);
}
my $data={version=>$RT::IR::VERSION,queues=>\%queues,bridge=>$bridge->Id};
write_private($marker,encode_json($data)."\n",33);
write_private('/run/bearings/secrets/rtir.json',encode_json($data)."\n",$uid);
print "Native RTIR queues/lifecycles and CIRCL-only credentials retained.\n";
